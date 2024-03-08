from acdc import patching_on_y, patching_on_downstream_feature
from ablation_utils import run_with_ablated_features
from loading_utils import load_submodule_and_dictionary, DictionaryCfg
from tqdm import tqdm
from copy import deepcopy
import torch as t

def _normalize_name(name):
    layer, feat_idx, submodule_type = name.split("_")
    return f"{submodule_type}_{layer}/{feat_idx}"


def evaluate_faithfulness(circuit_features, model, dict_cfg, eval_dataset, submodules_generic,
                          patch_type='zero'):
    """
    Evaluate performance of circuit compared to full model.
    `patch_type` can be one of the following:
    - "zero": sets activation to zero
    - "mean": sets activation to its mean over many Pile contexts (loads from .pkl)
    - "random": sets activation to what it would've been given a single Pile
                context (computed in-function)
    """
    if patch_type == "zero":
        patch_vector = t.zeros(dict_cfg.size)
    elif patch_type == "mean":
        raise NotImplementedError()
    elif patch_type == "random":
        raise NotImplementedError()
    
    # Pre-load all submodules and dictionaries
    num_layers = model.config.num_hidden_layers
    submodule_to_autoencoder = {}
    for layer in range(num_layers):
        for submodule_name in submodules_generic:
            submodule_name = submodule_name.format(str(layer))
            submodule, dictionary = load_submodule_and_dictionary(model, submodule_name, dict_cfg)
            submodule_to_autoencoder[submodule] = dictionary
    
    mean_faithfulness = 0.
    num_examples = len(eval_dataset)
    faithfulness_by_example = {}
    for example in tqdm(eval_dataset, desc="Evaluating faithfulness", total=len(eval_dataset)):
        with model.invoke(example["clean_prefix"]) as invoker:
            pass
        model_logit_diff = invoker.output.logits[:, -1, example["clean_answer"]] - \
                            invoker.output.logits[:, -1, example["patch_answer"]]

        circuit_out = run_with_ablated_features(model, example["clean_prefix"], dict_cfg.dir, dict_cfg.size,
                                                circuit_features, # submodule_to_autoencoder, 
                                                patch_vector=patch_vector, inverse=True)["model"]
        circuit_logit_diff = circuit_out.logits[:, -1, example["clean_answer"]] - \
                                circuit_out.logits[:, -1, example["patch_answer"]]
        faithfulness = circuit_logit_diff / model_logit_diff

        # print(example["clean_prefix"], example["clean_answer"])
        # example_sent = self.model.tokenizer.decode(example["clean_prefix"][0]) + " " + self.model.tokenizer.decode(example["clean_answer"])
        # faithfulness_by_example[example_sent] = faithfulness
        mean_faithfulness += faithfulness
    
    # sorted_faithfulness = {k: v for k, v in sorted(faithfulness_by_example.items(), key=lambda x: x[1])}
    # for example in sorted_faithfulness:
    #     print(f"{example}: {sorted_faithfulness[example]}")

    mean_faithfulness /= num_examples
    return mean_faithfulness.item()


def evaluate_completeness(circuit_features, model, dict_cfg, eval_dataset, submodules_generic,
                          patch_type='zero', K_size=10):
    """
    Evaluate whether we've found everything contributing to the logit diff.
    `patch_type` can be one of the following:
    - "zero": sets activation to zero
    - "mean": sets activation to its mean over many Pile contexts (loads from .pkl)
    - "random": sets activation to what it would've been given a single Pile
                context (computed in-function)
    """
    circuit_feature_set = set(circuit_features)

    if patch_type == "zero":
        patch_vector = t.zeros(dict_cfg.size)
    elif patch_type == "mean":
        raise NotImplementedError()
    elif patch_type == "random":
        raise NotImplementedError()

    # Pre-load all submodules and dictionaries
    num_layers = model.config.num_hidden_layers
    submodule_to_autoencoder = {}
    for layer in range(num_layers):
        for submodule_name in submodules_generic:
            submodule_name = submodule_name.format(str(layer))
            submodule, dictionary = load_submodule_and_dictionary(model, submodule_name, dict_cfg)
            submodule_to_autoencoder[submodule] = dictionary
    
    mean_percent_recovered = 0
    completeness_points = []
    mean_incompleteness = 0.
    total = 0
    K = circuit_feature_set
    num_examples = len(eval_dataset)

    # Greedy sampling by indirect effect
    # K = set()
    # num_examples = len(eval_dataset)
    # curr_parent = self.root
    # next_parents = []      # queue
    # for _ in tqdm(range(K_size), desc="Building K", total=K_size):
    #     curr_node = None
    #     while True:     # do-while loop
    #         max_effect = float("-inf")
    #         for child in curr_parent.children:
    #             next_parents.append(child)
    #             if self._normalize_name(child.name) in K:
    #                 continue
    #             if child.effect_on_parents[curr_parent] > max_effect:
    #                 max_effect = child.effect_on_parents[curr_parent]
    #                 curr_node = child
    #         if curr_node is None:
    #             curr_parent = next_parents.pop(0)
    #         if not (curr_node is None and len(next_parents) != 0):
    #             break
    #     if curr_node is None:
    #         print(f"No more nodes to add. Exiting loop w/ |K|={len(K)}")
    #     else:
    #         K.add(self._normalize_name(curr_node.name))

    # compute incompleteness
    model_no_K_diff = 0.
    circuit_features_no_K = circuit_feature_set.difference(K)
    completeness = 0.
    for example in tqdm(eval_dataset, desc="Evaluating completeness", total=len(eval_dataset)):
        model_no_K_out = run_with_ablated_features(model, example["clean_prefix"],
                                    dict_cfg.dir, dict_cfg.size,
                                    K, # submodule_to_autoencoder, 
                                    patch_vector=patch_vector, inverse=False)["model"]
        model_no_K_diff = model_no_K_out.logits[:, -1, example["clean_answer"]] - \
                            model_no_K_out.logits[:, -1, example["patch_answer"]]
        circuit_no_K_out = run_with_ablated_features(model, example["clean_prefix"],
                                                        dict_cfg.dir, dict_cfg.size,
                                                        list(circuit_features_no_K), # submodule_to_autoencoder,
                                                        patch_vector=patch_vector, inverse=True)["model"]
        circuit_no_K_diff = circuit_no_K_out.logits[:, -1, example["clean_answer"]] - \
                            circuit_no_K_out.logits[:, -1, example["patch_answer"]]
        completeness += circuit_no_K_diff / model_no_K_diff
    
    completeness /= num_examples
    completeness_points.append((circuit_no_K_diff.item(), model_no_K_diff.item()))
    return {"mean_completeness": completeness.item(),
            "completeness_points": completeness_points,
            "K": K}


# def evaluate_minimality(circuit_features, eval_dataset=None, patch_type='zero', K_size=10, sample_size=5):
#     if not eval_dataset:    # evaluate on train dataset
#         eval_dataset = self.dataset
#     circuit_feature_list = self.get_feature_list()
#     circuit_feature_set = set(circuit_feature_list)

#     if patch_type == "zero":
#         patch_vector = t.zeros(self.dict_cfg.size)
#     elif patch_type == "mean":
#         raise NotImplementedError()
#     elif patch_type == "random":
#         raise NotImplementedError()

#     # Pre-load all submodules and dictionaries
#     num_layers = self.model.config.num_hidden_layers
#     submodule_to_autoencoder = {}
#     for layer in range(num_layers):
#         for submodule_name in self.submodules_generic:
#             submodule_name = submodule_name.format(str(layer))
#             submodule, dictionary = load_submodule_and_dictionary(self.model, submodule_name, self.dict_cfg)
#             submodule_to_autoencoder[submodule] = dictionary
    
#     num_examples = len(eval_dataset)
#     minimality_per_node = {}
#     min_minimality = float("inf")
#     for node in tqdm(circuit_feature_list, desc="Evaluating minimality", total=len(circuit_feature_list)):
#         circuit_features_without_node = deepcopy(circuit_feature_set)
#         circuit_features_without_node.remove(node)
#         mean_minimality = 0.
#         for example in eval_dataset:
#             circuit_out = run_with_ablated_features(self.model, example["clean_prefix"],
#                                                         self.dict_cfg.dir, self.dict_cfg.size,
#                                                         list(circuit_feature_set), submodule_to_autoencoder,
#                                                         patch_vector=patch_vector, inverse=True)["model"]
#             circuit_diff = circuit_out.logits[:, -1, example["clean_answer"]] - \
#                             circuit_out.logits[:, -1, example["patch_answer"]]
#             circuit_without_node_out = run_with_ablated_features(self.model, example["clean_prefix"],
#                                                         self.dict_cfg.dir, self.dict_cfg.size,
#                                                         list(circuit_features_without_node), submodule_to_autoencoder,
#                                                         patch_vector=patch_vector, inverse=True)["model"]
#             circuit_without_node_diff = circuit_without_node_out.logits[:, -1, example["clean_answer"]] - \
#                                         circuit_without_node_out.logits[:, -1, example["patch_answer"]]
#             minimality = 1 - (circuit_without_node_diff / circuit_diff)
#             mean_minimality += minimality
#         mean_minimality /= num_examples
#         minimality_per_node[node] = mean_minimality.item() / len(circuit_feature_list)
#         min_minimality = min(minimality_per_node[node], min_minimality)

#     return {"min_minimality": min_minimality,
#             "minimality_per_node": minimality_per_node}


def evaluate_minimality(circuit_features):
    return -len(circuit_features)


def load_triangles_circuit(circuit_path, n_layers):
    with open(circuit_path, "rb") as handler:
        circuit = t.load(handler)
    
    node_threshold = float(circuit_path.split("node")[1].split("_")[0])

    circuit_nodes = circuit["nodes"]
    feature_list = []
    for submodtype in ["mlp", "attn", "resid"]:
        for layer in range(n_layers):
            submodname = f"{submodtype}_{layer}"
            idxs = (circuit_nodes[submodname].act > node_threshold).nonzero().flatten()
            for idx in idxs:
                feature_list.append(f"{submodtype}_{layer}/{idx}")
    return feature_list


if __name__ == "__main__":
    import argparse
    from nnsight import LanguageModel
    from loading_utils import load_examples

    parser = argparse.ArgumentParser()
    parser.add_argument("circuit_path", type=str)
    parser.add_argument("--model", type=str, default="EleutherAI/pythia-70m-deduped")
    parser.add_argument("--dataset", type=str, default="/share/projects/dictionary_circuits/data/phenomena/simple_test.json")

    args = parser.parse_args()

    model = LanguageModel(args.model, device_map="cuda:0")
    n_layers = model.config.num_hidden_layers
    dataset = load_examples(args.dataset, 100, model)

    dict_cfg = DictionaryCfg("/share/projects/dictionary_circuits/autoencoders/pythia-70m-deduped/",
                             32768)
    submodules_generic = ["model.gpt_neox.layers.{}.attention.dense", "model.gpt_neox.layers.{}.mlp.dense_4h_to_h",
                          "model.gpt_neox.layers.{}"]

    circuit_features = load_triangles_circuit(args.circuit_path, n_layers)

    faithfulness = evaluate_faithfulness(circuit_features, model, dict_cfg, dataset, submodules_generic)
    completeness = evaluate_completeness(circuit_features, model, dict_cfg, dataset, submodules_generic)
    minimality = evaluate_minimality(circuit_features)

    print("faithfulness:", faithfulness)
    print("completeness:", completeness["mean_completeness"])
    print("minimality:", minimality)