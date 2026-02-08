#!/bin/bash
# TripTailor 评测脚本

# 配置
MODEL_NAME="deepseek_chat"
STRATEGY="direct"
PLAN_KEY="${MODEL_NAME}_${STRATEGY}"

INPUT_FILE="../outputs/${PLAN_KEY}_result.json"
INFO_FILE="../../data/infomation.json"
OUTPUT_FILE="../outputs/${PLAN_KEY}_eval_result.json"

# 是否启用事实验证 (需要联网)
ENABLE_FACT_CHECK=false
FACT_CHECK_SAMPLES=5

# 运行评测
echo "Running evaluation for ${PLAN_KEY}..."

if [ "$ENABLE_FACT_CHECK" = true ]; then
    python simple_eval.py \
        --input_file "$INPUT_FILE" \
        --plan_key "$PLAN_KEY" \
        --info_file "$INFO_FILE" \
        --output_file "$OUTPUT_FILE" \
        --enable_fact_check \
        --fact_check_samples $FACT_CHECK_SAMPLES \
        --detail
else
    python simple_eval.py \
        --input_file "$INPUT_FILE" \
        --plan_key "$PLAN_KEY" \
        --info_file "$INFO_FILE" \
        --output_file "$OUTPUT_FILE" \
        --detail
fi

echo "Evaluation complete. Results saved to ${OUTPUT_FILE}"



