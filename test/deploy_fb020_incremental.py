"""FB-020 增量部署：anthropic/responses 入站补图片块映射（2 个后端文件，无前端/DB 变更），重启并验证"""
import os
import sys

import paramiko

SSH_PASS = os.environ.get("SR_SSH_PASS", "")

BACKEND_FILES = [
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

    print("[1] 上传 2 个后端文件")
    for rel in BACKEND_FILES:
        src = os.path.join(LOCAL_BACKEND, rel)
        dst = f"{REMOTE_BACKEND}/{rel.replace(os.sep, '/')}"
        sftp.put(src, dst)
        print(f"  up {dst} ({os.path.getsize(src)}B)")

    print("[2] 语法预检")
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -m py_compile "
                      "app/upstream/anthropic_adapter.py app/upstream/responses_adapter.py && echo COMPILE_OK"))

    print("[3] 重启服务")
    print(run(client, "systemctl restart smart-router && sleep 5 && systemctl is-active smart-router"))
    print(run(client, "curl -s -o /dev/null -w 'GET / -> %{http_code}\\n' http://127.0.0.1:10002/"))

    print("[4] 生产端图片转换验证（anthropic image 块 + responses input_image 块）")
    probe = (
        "from app.upstream.anthropic_adapter import convert_request_anthropic_to_openai as a;"
        "from app.upstream.responses_adapter import convert_request_responses_to_openai as r;"
        "b={'model':'m','max_tokens':10,'messages':[{'role':'user','content':[{'type':'text','text':'x'},"
        "{'type':'image','source':{'type':'base64','media_type':'image/png','data':'QQ=='}}]}]};"
        "c=a(b)['messages'][0]['content'];"
        "assert isinstance(c,list) and c[1]=={'type':'image_url','image_url':{'url':'data:image/png;base64,QQ=='}};"
        "rb={'model':'m','input':[{'type':'message','role':'user','content':[{'type':'input_text','text':'y'},"
        "{'type':'input_image','image_url':'https://x/y.png'}]}]};"
        "rc=r(rb)['messages'][0]['content'];"
        "assert isinstance(rc,list) and rc[1]=={'type':'image_url','image_url':{'url':'https://x/y.png'}};"
        "print('PROD_CONVERT_OK')"
    )
    print(run(client, f"cd {REMOTE_BACKEND} && /root/miniconda3/bin/python -c \"{probe}\""))

    print("[5] /v1/messages 与 /v1/responses 路由存活（无 Key 应 401 而非 404）")
    print(run(client, "curl -s -o /dev/null -w 'POST /v1/messages -> %{http_code}\\n' -X POST http://127.0.0.1:10002/v1/messages -H 'Content-Type: application/json' -d '{}'"))
    print(run(client, "curl -s -o /dev/null -w 'POST /v1/responses -> %{http_code}\\n' -X POST http://127.0.0.1:10002/v1/responses -H 'Content-Type: application/json' -d '{}'"))

    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
