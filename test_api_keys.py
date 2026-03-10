"""API Key 可用性检测脚本"""
import os, sys, json

from dotenv import load_dotenv
load_dotenv('.env')

print('=' * 60)
print('API Key 检测报告')
print('=' * 60)

# 1. 测试 DeepSeek API Key
print('\n[1/4] 测试 DeepSeek API Key...')
deepseek_key = os.getenv('DEEPSEEK_API_KEY', '')
deepseek_base = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
if deepseek_key:
    try:
        import requests
        resp = requests.post(
            f'{deepseek_base}/chat/completions',
            headers={'Authorization': f'Bearer {deepseek_key}', 'Content-Type': 'application/json'},
            json={'model': 'deepseek-chat', 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 5},
            timeout=15
        )
        if resp.status_code == 200:
            print('  [OK] DeepSeek API Key 有效 (状态码: 200)')
        else:
            try:
                err = resp.json()
            except Exception:
                err = resp.text[:200]
            print(f'  [FAIL] DeepSeek API Key 无效 (状态码: {resp.status_code})')
            print(f'     错误: {err}')
    except Exception as e:
        print(f'  [FAIL] DeepSeek API Key 测试失败: {e}')
else:
    print('  [WARN] DEEPSEEK_API_KEY 未配置')

# 2. 测试高德地图 API Key
print('\n[2/4] 测试高德地图 API Key...')
amap_key = os.getenv('AMAP_API_KEY', '')
if amap_key:
    try:
        import requests
        resp = requests.get(
            'https://restapi.amap.com/v3/config/district',
            params={'key': amap_key, 'keywords': '北京', 'subdistrict': '0'},
            timeout=10
        )
        data = resp.json()
        status = data.get('status')
        info = data.get('info', '')
        infocode = data.get('infocode', '')
        if status == '1':
            print(f'  [OK] 高德地图 API Key 有效 (info: {info})')
        else:
            print(f'  [FAIL] 高德地图 API Key 无效 (info: {info}, infocode: {infocode})')
    except Exception as e:
        print(f'  [FAIL] 高德地图 API Key 测试失败: {e}')
else:
    print('  [WARN] AMAP_API_KEY 未配置')

# 3. 测试 Search API Key
print('\n[3/4] 测试 Search API Key...')
search_key = os.getenv('SEARCH_API', '') or os.getenv('SEARCH_API_KEY', '')
if search_key:
    print(f'  [INFO] Search API Key 已配置 (前缀: {search_key[:6]}...)')
    try:
        import requests
        resp = requests.get(
            'https://serpapi.com/search',
            params={'api_key': search_key, 'q': 'test', 'engine': 'google'},
            timeout=10
        )
        if resp.status_code == 200:
            print(f'  [OK] Search API Key 有效 (SerpAPI, 状态码: 200)')
        else:
            print(f'  [WARN] SerpAPI 返回状态码 {resp.status_code}')
            print(f'     响应: {resp.text[:200]}')
    except Exception as e:
        print(f'  [WARN] Search API Key 连接测试异常: {e}')
else:
    print('  [WARN] SEARCH_API 未配置')

# 4. 测试 TripTailor OpenAI API Key (VectorEngine)
print('\n[4/4] 测试 TripTailor OpenAI API Key (VectorEngine)...')
load_dotenv('TripTailor/.env', override=True)
openai_key = os.getenv('OPENAI_API_KEY', '')
openai_base = os.getenv('OPENAI_BASE_URL', '')
if openai_key and openai_base:
    try:
        import requests
        resp = requests.get(
            f'{openai_base}/models',
            headers={'Authorization': f'Bearer {openai_key}'},
            timeout=10
        )
        if resp.status_code == 200:
            models = resp.json()
            model_count = len(models.get('data', [])) if isinstance(models, dict) else 0
            print(f'  [OK] OpenAI (VectorEngine) API Key 有效 (可用模型数: {model_count})')
        else:
            err = resp.text[:200]
            print(f'  [FAIL] OpenAI (VectorEngine) API Key 无效 (状态码: {resp.status_code})')
            print(f'     错误: {err}')
    except Exception as e:
        print(f'  [FAIL] OpenAI (VectorEngine) API Key 测试失败: {e}')
elif openai_key:
    print('  [WARN] OPENAI_API_KEY 已配置但 OPENAI_BASE_URL 未设置')
else:
    print('  [WARN] OPENAI_API_KEY (TripTailor) 未配置')

print('\n' + '=' * 60)
print('检测完成')
print('=' * 60)
