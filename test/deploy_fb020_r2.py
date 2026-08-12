"""FB-020 二期增量部署：错误格式包装 + reasoning/thinking 映射（5 个后端文件），重启并验证"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

BACKEND_FILES = [
    r"app\api\v1\messages.py",
    r"app\api\v1\responses.py",
    r"app\api\v1\chat.py",
    r"app\upstream\anthropic_adapter.py",
    r"app\upstream\responses_adapter.py",
]
LOCAL_BACKEND = r"E:\80-project_dev\04_smart-router(starting)\backend"
REMOTE_BACKEND = "/opt/smart-router/backend"


def run(client, cmd, timeout=60) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return (stdout.read().decode("utf-8", "ignore") + stderr.read().decode("utf-8", "ignore")).strip()


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("8.137.195.192", 22, "root", SSH_PASS, timeout=15)
    sftp = client.open_sftp()

    print("[1] 上传 5 个后端文件")
    for rel in BACKEND_FILES:
        src = os.path.join(LOCAL_BACKEND, rel)
        dst = f"{REMOTE_BACKEND}/{rel.replace(os.sep, '/')}"
        sftp.put(src, dst)
        print(f"  up {dst} ({os.path.getsize(src)}B)")

    print("[2] 语法预检")
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -m py_compile "
                      "app/api/v1/messages.py app/api/v1/responses.py app/api/v1/chat.py "
                      "app/upstream/anthropic_adapter.py app/upstream/responses_adapter.py && echo COMPILE_OK"))

    print("[3] 重启服务")
    print(run(client, "systemctl restart smart-router && sleep 5 && systemctl is-active smart-router"))
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))

    print("[4] 生产端转换单测（错误格式函数 + thinking 映射）")
    probe = (
        "from app.api.v1.messages import _anthropic_error as ae;"
        "from app.api.v1.responses import _responses_error as re;"
        "from app.api.v1.chat import _openai_error as oe;"
        "import json;"
        "assert json.loads(ae(503,'x').body.decode())['error']['type']=='api_error';"
        "assert json.loads(re(503,'x').body.decode())['error']['type']=='api_error';"
        "assert json.loads(oe(503,'x').body.decode())['error']['message']=='x';"
        "from app.upstream.anthropic_adapter import OpenaiToAnthropicSSE;"
        "c=OpenaiToAnthropicSSE('m');"
        "ch=lambda d,f=None:{'choices':[{'index':0,'delta':d,'finish_reason':f}]};"
        "evs=[];"
        "evs+=c.feed('data: '+json.dumps(ch({'role':'assistant','content':''}))+chr(10)+chr(10));"
        "evs+=c.feed('data: '+json.dumps(ch({'reasoning_content':'r1'}))+chr(10)+chr(10));"
        "evs+=c.feed('data: '+json.dumps(ch({'content':'ok'}))+chr(10)+chr(10));"
        "evs+=c.feed('data: '+json.dumps(ch({},'stop'))+chr(10)+chr(10));"
        "s=''.join(evs);"
        "assert 'thinking_delta' in s and 'text_delta' in s;"
        "print('PROD_R2_OK')"
    )
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -c \"{probe}\""))

    print("[5] 三个入站路由存活（无 Key 应 401 而非 404）")
    print(run(client, "curl -s -o /dev/null -w 'POST /v1/messages -> %{http_code}\\n' -X POST http://127.0.0.1:10002/v1/messages -H 'Content-Type: application/json' -d '{}'"))
    print(run(client, "curl -s -o /dev/null -w 'POST /v1/responses -> %{http_code}\\n' -X POST http://127.0.0.1:10002/v1/responses -H 'Content-Type: application/json' -d '{}'"))
    print(run(client, "curl -s -o /dev/null -w 'POST /v1/chat/completions -> %{http_code}\\n' -X POST http://127.0.0.1:10002/v1/chat/completions -H 'Content-Type: application/json' -d '{}'"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
