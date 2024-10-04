#!/bin/bash

MODEL=$1
CIRCUIT=$2
EVAL_DATA=$3
THRESHOLD=$4

# Run the ablation.py script with the specified arguments
python ablation.py \
--model $MODEL \
--circuit $CIRCUIT \
--data ${EVAL_DATA} \
--threshold $THRESHOLD \
--ablation mean \
--handle_errors 'default' \
--start_layer 6 \
--nopair_reg \
--device cuda:0