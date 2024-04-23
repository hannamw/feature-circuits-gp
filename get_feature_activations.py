#%%
from typing import Dict

import torch 
from torch import Tensor

# %%
def get_feature_activations(feature_dict: Dict[str, Tensor], circuit_name: str):
    activations = {}
    circuit = torch.load(f'circuits/{circuit_name}.pt')
    for node, features in feature_dict.items():
        activations[node] = circuit['nodes'][node].act[features[:, 0], features[:, 1]]
    return activations

#%%
circuit_name = 'NPS_post_samelen_dict10_node0.1_edge0.01_n24_aggnone'
fd = {'embed': torch.tensor([[0, 13487], [2, 8402], [2,18619], [2, 13847]])}
activations = get_feature_activations(fd, circuit_name)