#!/bin/bash
# TravelPlanner 评测脚本

# 配置
SET_TYPE="validation"  # train, validation, test
EVALUATION_FILE="../postprocess/example_evaluation.jsonl"
OUTPUT_FILE="eval_results.json"

# 事实验证配置 (可选)
ENABLE_FACT_CHECK=false
FACT_CHECK_SAMPLES=5

# 运行评测
echo "Running TravelPlanner evaluation..."
echo "  Dataset: ${SET_TYPE}"
echo "  File: ${EVALUATION_FILE}"

if [ "$ENABLE_FACT_CHECK" = true ]; then
    python simple_eval.py \
        --set_type "$SET_TYPE" \
        --evaluation_file_path "$EVALUATION_FILE" \
        --output_file "$OUTPUT_FILE" \
        --enable_fact_check \
        --fact_check_samples $FACT_CHECK_SAMPLES
else
    python simple_eval.py \
        --set_type "$SET_TYPE" \
        --evaluation_file_path "$EVALUATION_FILE" \
        --output_file "$OUTPUT_FILE"
fi

echo "Evaluation complete. Results saved to ${OUTPUT_FILE}"



