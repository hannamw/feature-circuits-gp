import argparse
import torch
from activation_utils import SparseAct

def _parse_feat_info(feat, submodule):
    pos, feat_idx = feat
    featname = f"{pos}, {submodule}/{feat}"
    return featname

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("circuit_1", type=str)
    parser.add_argument("circuit_2", type=str)
    args = parser.parse_args()

    start_pos = 1

    c1 = torch.load(args.circuit_1)
    t_n1 = float(args.circuit_1.split("_node")[1].split(".pt")[0])
    c2 = torch.load(args.circuit_2)
    t_n2 = float(args.circuit_2.split("_node")[1].split(".pt")[0])
    c1_featset = set()
    c2_featset = set()

    c1_in_c2_ie_sum = 0.
    c2_in_c2_ie_sum = 0.
    for submodule in c1["nodes"]:
        c1_feats = (c1["nodes"][submodule].act[start_pos:].abs() > t_n1).nonzero().tolist()
        c2_feats = (c2["nodes"][submodule].act[start_pos:].abs() > t_n2).nonzero().tolist()
        for feat in c1_feats:
            featname = _parse_feat_info(feat, submodule)
            c1_featset.add(featname)
            c1_in_c2_ie_sum += c2["nodes"][submodule].act[start_pos:].abs()[feat[0], feat[1]].item()
        for feat in c2_feats:
            featname = _parse_feat_info(feat, submodule)
            c2_featset.add(featname)
            c2_in_c2_ie_sum += c2["nodes"][submodule].act[start_pos:].abs()[feat[0], feat[1]].item()
    
    n1 = len(c1_featset)
    n2 = len(c2_featset)
    intersection_size = len(c1_featset.intersection(c2_featset))
    iou = intersection_size / len(c1_featset.union(c2_featset))
    
    print(f"# nodes in circuit 1: {n1}")
    print(f"# nodes in circuit 2: {n2}")
    print(f"# nodes in intersection: {intersection_size}")
    print(f"IoU: {iou}")

    print(f"effect of c1 nodes in c2: {c1_in_c2_ie_sum}")
    print(f"effect of c2 nodes in c2: {c2_in_c2_ie_sum}")
    print(f"effect ratio: {c1_in_c2_ie_sum / c2_in_c2_ie_sum}")