# Smart Router v5 管理接口自动化测试脚本
# 用法：powershell -ExecutionPolicy Bypass -File test_api.ps1
# 前置：后端已启动 (uv run python run.py)

$ErrorActionPreference = "Stop"
$base = "http://localhost:10002"

$passCount = 0
$failCount = 0

function Assert-Test($name, $cond, $detail) {
    if ($cond) {
        $script:passCount++
        Write-Host "  [PASS] $name" -ForegroundColor Green
    } else {
        $script:failCount++
        Write-Host "  [FAIL] $name - $detail" -ForegroundColor Red
    }
}

Write-Host "===== 1. 登录 ====="
$login = Invoke-RestMethod -Uri "$base/admin/api/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"smart-router-2026"}'
Assert-Test "登录返回 token" ($null -ne $login.token) $login
$h = @{ Authorization = "Bearer $($login.token)" }

Write-Host "===== 2. 仪表盘 ====="
$dash = Invoke-RestMethod -Uri "$base/admin/api/dashboard" -Headers $h
Assert-Test "上游源数 >= 1" ($dash.upstream_count -ge 1) $dash

Write-Host "===== 3. 上游源 CRUD ====="
$ups = Invoke-RestMethod -Uri "$base/admin/api/upstreams" -Headers $h
Assert-Test "上游源列表非空" ($ups.upstreams.Count -ge 1) "count=$($ups.upstreams.Count)"
Assert-Test "密钥已脱敏" ($ups.upstreams[0].api_key -match "\*") "key=$($ups.upstreams[0].api_key)"

Write-Host "===== 4. 添加/删除上游源 ====="
$testId = "test-up-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$addBody = @{ id=$testId; name="Test"; base_url="http://127.0.0.1:9999"; api_key="sk-test"; format="openai" } | ConvertTo-Json
$add = Invoke-RestMethod -Uri "$base/admin/api/upstreams" -Method Post -Headers $h -ContentType "application/json" -Body $addBody
Assert-Test "添加上游源成功" ($add.ok -eq $true) $add
$del = Invoke-RestMethod -Uri "$base/admin/api/upstreams/$testId" -Method Delete -Headers $h
Assert-Test "删除上游源成功" ($del.ok -eq $true) $del

Write-Host "===== 5. 路由规则 ====="
$rules = Invoke-RestMethod -Uri "$base/admin/api/rules" -Headers $h
Assert-Test "规则列表非空" ($rules.rules.Count -ge 1) "count=$($rules.rules.Count)"

Write-Host "===== 6. API Key 管理 ====="
$keys = Invoke-RestMethod -Uri "$base/admin/api/api-keys" -Headers $h
Assert-Test "API Key 列表非空" ($keys.api_keys.Count -ge 1) "count=$($keys.api_keys.Count)"

Write-Host "===== 7. 模型别名 ====="
$pt = Invoke-RestMethod -Uri "$base/admin/api/model-pointers" -Headers $h
Assert-Test "别名列表非空" ($pt.pointers.Count -ge 1) "count=$($pt.pointers.Count)"

Write-Host "===== 8. 聚合模型名 ====="
$agg = Invoke-RestMethod -Uri "$base/admin/api/aggregated-names" -Headers $h
Assert-Test "聚合名非空" ($agg.names.Count -ge 1) "count=$($agg.names.Count)"

Write-Host "===== 9. 系统参数 ====="
$probe = Invoke-RestMethod -Uri "$base/admin/api/config/probe" -Headers $h
Assert-Test "探测配置可读" ($null -ne $probe.interval_seconds) $probe
$retry = Invoke-RestMethod -Uri "$base/admin/api/config/retry" -Headers $h
Assert-Test "重试配置可读" ($null -ne $retry.max_attempts) $retry

Write-Host "===== 10. 热重载 ====="
$reload = Invoke-RestMethod -Uri "$base/admin/api/reload" -Method Post -Headers $h
Assert-Test "热重载成功" ($reload.ok -eq $true) $reload

Write-Host "===== 11. 客户端鉴权 ====="
try {
    Invoke-RestMethod -Uri "$base/v1/chat/completions" -Method Post -ContentType "application/json" -Body '{"model":"smart-latest","messages":[{"role":"user","content":"hi"}]}' -ErrorAction Stop | Out-Null
    Assert-Test "无 Key 返回 401" $false "未返回 401"
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    Assert-Test "无 Key 返回 401" ($status -eq 401) "got=$status"
}

Write-Host "===== 12. 修改密码（旧密码改回） ====="
$pwd = Invoke-RestMethod -Uri "$base/admin/api/admin-password" -Method Put -Headers $h -ContentType "application/json" -Body '{"old_password":"smart-router-2026","new_password":"smart-router-2026"}'
Assert-Test "修改密码成功" ($pwd.ok -eq $true) $pwd

Write-Host ""
Write-Host "===== 结果: $passCount 通过, $failCount 失败 =====" -ForegroundColor $(if ($failCount -eq 0) { "Green" } else { "Red" })
exit $failCount
