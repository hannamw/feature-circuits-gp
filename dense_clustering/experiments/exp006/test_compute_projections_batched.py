"""
This script computes a similarity matrix between samples using batches.
"""

import os
from collections import defaultdict
import pickle
import h5py

import numpy as np
from tqdm.auto import tqdm

import torch as t
import torch.nn.functional as F

import datasets
from transformers import AutoTokenizer, GPTNeoXForCausalLM

# DEFINE SOME PARAMETERS
MODEL_NAME = "pythia-70m"
STEP = 142_000
CACHE_DIR = f"/om/user/ericjm/pythia-models/{MODEL_NAME}/step{STEP}"
SKIP = 5
N_SAMPLES = 500
CHUNK_SIZE = 250 # frequency of saving the gradients to hdf5
BATCH_SIZE = 5
PROJECTION_DIM = 30_000
DENSITY_FACTOR = 16
SAVE_DIR = "/om2/user/ericjm/dictionary-circuits/dense_clustering/experiments/exp006/tmp"
device = t.device('cuda:0') if t.cuda.is_available() else 'cpu'
t.set_default_dtype(t.float32)

assert N_SAMPLES % CHUNK_SIZE == 0, "N_SAMPLES must be a multiple of CHUNK_SIZE"
assert CHUNK_SIZE % BATCH_SIZE == 0, "CHUNK_SIZE must be a multiple of BATCH_SIZE"

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# SET ALL SEEDS HERE
t.manual_seed(0)
t.cuda.manual_seed(0)
np.random.seed(0)

######################
# Load up the dataset
######################
pile_canonical = "/om/user/ericjm/the_pile/the_pile_test_canonical_200k"
dataset = datasets.load_from_disk(pile_canonical)

starting_indexes = np.array([0] + list(np.cumsum(dataset["preds_len"])))

def loss_idx_to_dataset_idx(idx):
    """given an idx, return a document index and pred-in-sample
    index in range(0, 1023). Note token-in-sample idx is
    exactly pred-in-sample + 1. So the pred_in_sample_index is the index
    into the sequence above will the model will genenerate a prediction for the
    token at the pred_in_sample_index + 1."""
    sample_index = np.searchsorted(starting_indexes, idx, side="right") - 1
    pred_in_sample_index = idx - starting_indexes[sample_index]
    return int(sample_index), int(pred_in_sample_index)

def get_context(idx):
    """given idx, return dataset document and the index of the token 
    corresponding to the given idx within that document, in range(1, 1024)."""
    sample_index, pred_index = loss_idx_to_dataset_idx(idx)
    return dataset[sample_index], pred_index+1

##############################
# Load up model and tokenizer
##############################
model = GPTNeoXForCausalLM.from_pretrained(
        f"EleutherAI/{MODEL_NAME}",
        revision=f"step{STEP}",
        cache_dir=CACHE_DIR,
    ).to(device)

tokenizer = AutoTokenizer.from_pretrained(
    f"EleutherAI/{MODEL_NAME}",
    revision=f"step{STEP}",
    cache_dir=CACHE_DIR,
)
tokenizer.pad_token = tokenizer.eos_token

class SparseProjectionOperator:
    """
    Note: I think the sparsity is off by a factor of two here.
    """
    def __init__(self, original_dim, projection_dim, sparsity, seed=0, device='cpu'):
        t.manual_seed(seed)
        t.cuda.manual_seed(seed) # if 'cuda' in device else None
        self.device = t.device(device)
        self.original_dim = original_dim
        self.lambda_ = original_dim * (1 - sparsity)
        num_entries = t.poisson(self.lambda_ * t.ones(projection_dim, device=device)).int()
        max_entries = num_entries.max()
        self.positives = t.randint(0, original_dim, (projection_dim, max_entries), device=device)
        self.negatives = t.randint(0, original_dim, (projection_dim, max_entries), device=device)
        masks = t.arange(max_entries, device=device).expand(projection_dim, max_entries) < num_entries.unsqueeze(-1)
        self.positives = self.positives * masks
        self.negatives = self.negatives * masks

    def __call__(self, x):
        # assert x.device == self.device, "device mismatch between projection and input"
        assert x.shape[-1] == self.original_dim, "input dimension mismatch"
        y = x[self.positives].sum(-1) - x[self.negatives].sum(-1)
        return y

############################  
# Select samples to cluster
############################
with open("/om2/user/ericjm/dictionary-circuits/dense_clustering/experiments/exp006/zero_and_induction_idxs-pythia-70m.pkl", "rb") as f:
    non_induction_zeros, zero_idxs, induction_idxs = pickle.load(f)
idxs = non_induction_zeros[::SKIP][:N_SAMPLES]

if len(idxs) != N_SAMPLES:
    print(f"ERROR: only {len(idxs)} samples available")
    exit()


def get_flattened_gradient(model, param_subset):
    grads = []
    for name, p in model.named_parameters():
        if name in param_subset:
            grads.append(p.grad)
    return t.cat([g.flatten() for g in grads])

param_names = [n for n, _ in model.named_parameters()]
highsignal_names = [name for name in param_names if
                        ('layernorm' not in name) and
                        ('embed' not in name)]

len_g = sum(model.state_dict()[name].numel() for name in highsignal_names)
print(f"len_g = {len_g}")

sparse_projector = SparseProjectionOperator(len_g, PROJECTION_DIM, 1 - (DENSITY_FACTOR / PROJECTION_DIM), device=device)

############################
# Compute similarity matrix
############################
Gs = t.zeros((CHUNK_SIZE, PROJECTION_DIM), dtype=t.float32, device=device)
model.eval()
with h5py.File(os.path.join(SAVE_DIR, f"gradients_batched.h5"), "a") as f:
    h5dset = f.create_dataset("gradients", (N_SAMPLES, PROJECTION_DIM),
        chunks=(CHUNK_SIZE, PROJECTION_DIM), dtype=np.float32)

    for i in tqdm(range(0, N_SAMPLES, BATCH_SIZE)):
        batch_idxs = idxs[i:i+BATCH_SIZE]
        # create tokens for the whole batch
        prompts = []
        ls = []
        for idx in batch_idxs:
            document, l = get_context(idx)
            prompt = document['text']
            prompts.append(prompt)
            ls.append(l)
        tokens = tokenizer(prompts, return_tensors='pt', max_length=1024, padding=True, truncation=True).to(device)
        # forward the batch
        logits = model(**tokens).logits
        targets = tokens.input_ids
        # backwards on each sample in the batch
        for b in range(BATCH_SIZE):
            model.zero_grad()
            l = ls[b]
            losses = t.nn.functional.cross_entropy(logits[b, :-1, :], targets[b, 1:], reduction='none')
            loss = losses[l-1]
            loss.backward(retain_graph=True)
            g = get_flattened_gradient(model, highsignal_names)
            g_projected = sparse_projector(g)
            Gs[i + b] = g_projected.detach()

        if (i + BATCH_SIZE) % CHUNK_SIZE == 0:
            chunk_start = i - (i % CHUNK_SIZE)
            h5dset[chunk_start:chunk_start+CHUNK_SIZE] = Gs.cpu().numpy()
            Gs.zero_()

# save the idxs 
with open(os.path.join(SAVE_DIR, "idxs_batched.pkl"), "wb") as f:
    pickle.dump(idxs, f)
