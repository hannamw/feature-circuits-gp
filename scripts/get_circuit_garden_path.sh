#!/bin/bash

NODE=0.1
EDGE=0.01

#declare -a arr=("NPZ_ambiguous_samelen" "NPS_ambiguous_samelen" "MVRR_ambiguous_samelen")

# you can also look for the MVRR circuit! But be careful for the reasons discussed in the paper (low probability assigned to both continuations)
declare -a arr=("NPZ_ambiguous_samelen" "NPS_ambiguous_samelen")

for DATA in "${arr[@]}"
do
    if [ $DATA == "NPZ_ambiguous_samelen" ]; then
        LEN=6
    elif [ $DATA == "NPS_ambiguous_samelen" ]; then
        LEN=5
    elif [ $DATA == "MVRR_ambiguous_samelen" ]; then
        LEN=5
    fi
    python circuit.py \
        --model EleutherAI/pythia-70m-deduped \
        --num_examples 100 \
        --batch_size 10 \
        --dataset $DATA \
        --node_threshold $NODE \
        --edge_threshold $EDGE \
        --aggregation none \
        --example_length $LEN \
        --nopair_reg \
        --annotations_file "annotations/all_pythia_annotations.jsonl"
done