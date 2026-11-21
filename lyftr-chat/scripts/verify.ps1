param([string]$BaseUrl = "http://localhost:8000")
$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")
$run = [Guid]::NewGuid().ToString("N")
function Check($ok, $description) {
    if (-not $ok) { throw "Failed: $description" }
    Write-Host "PASS  $description"
}
function Send-Turn($session, $message, $simulation = "") {
    $headers = @{}
    if ($simulation) { $headers["X-Simulate-Failure"] = $simulation }
    $json = @{session_id=$session; message=$message} | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/chat" -ContentType "application/json" -Headers $headers -Body $json
}
$health = Invoke-RestMethod "$BaseUrl/health"
Check ($health.status -eq "ok" -and $health.keys_configured -ge 2 -and $health.cache_enabled) "health and key pool"
$question = "My reference is $run. Reply with just that reference."
$a = Send-Turn "a-$run" $question
$b = Send-Turn "b-$run" $question
$a.metadata, $b.metadata | Format-Table resolution_source, model, latency_ms, input_tokens, output_tokens, key_id, fallback_attempts
Check ($a.metadata.resolution_source -eq "LIVE_INFERENCE") "first request ran live"
Check ($b.metadata.resolution_source -eq "LLM_CACHE" -and $a.reply -ceq $b.reply -and $null -eq $b.metadata.key_id -and $b.metadata.fallback_attempts -eq 0) "cross-session cache hit"
Check ($a.metadata.input_tokens -eq $b.metadata.input_tokens -and $a.metadata.output_tokens -eq $b.metadata.output_tokens) "cache preserved provider token counts"
Check ($b.metadata.latency_ms -lt $a.metadata.latency_ms) "cache hit faster than inference"
$c = Send-Turn "a-$run" "Repeat my reference."
Write-Host "Follow-up: $($c.reply)"
$c.metadata | Format-List
foreach ($status in 429,500) {
    $f = Send-Turn "f-$status-$run" $question "key_1=$status"
    Check ($f.metadata.key_id -eq "key_2" -and $f.metadata.fallback_attempts -eq 1 -and $f.reply) "key_2 answered after simulated $status"
}
try {
    $null = Send-Turn "a-$run" "discard this" "*=429"
    throw "Expected all providers to fail"
} catch {
    if ([int]$_.Exception.Response.StatusCode -ne 503) { throw }
    Write-Host "PASS  all keys failed with HTTP 503"
}
$history = Invoke-RestMethod "$BaseUrl/sessions/a-$run/messages"
Check ($history.messages.Count -eq 4 -and $history.messages[-1].content -ceq $c.reply) "two turns persisted; failed turn absent"
Write-Host "History: $BaseUrl/sessions/a-$run/messages"
