$ErrorActionPreference = "Stop"

$baseUrl = "http://127.0.0.1:5001"
$pollIntervalMs = 1000
$maxPollAttempts = 180

$payload = @{
    text = "Hello world. This is a local async job API smoke test."
    language = "en"
} | ConvertTo-Json -Compress

$headers = @{
    "Content-Type" = "application/json; charset=utf-8"
}

Write-Host "Submitting job to $baseUrl/tts/jobs ..."
$submitResponse = Invoke-RestMethod -Uri "$baseUrl/tts/jobs" -Method POST -Body $payload -Headers $headers

$jobId = [string]$submitResponse.id
if ([string]::IsNullOrWhiteSpace($jobId)) {
    throw "Submit response did not include job id."
}

Write-Host "Job ID: $jobId"

$finalStatus = $null
for ($attempt = 1; $attempt -le $maxPollAttempts; $attempt++) {
    $statusResponse = Invoke-RestMethod -Uri "$baseUrl/tts/jobs/$jobId" -Method GET
    $status = [string]$statusResponse.status
    $processed = $statusResponse.processed_chunks
    $total = $statusResponse.total_chunks

    Write-Host ("[{0}/{1}] status={2} processed={3} total={4}" -f $attempt, $maxPollAttempts, $status, $processed, $total)

    if ($status -in @("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT")) {
        $finalStatus = $status
        break
    }

    Start-Sleep -Milliseconds $pollIntervalMs
}

if ($finalStatus -ne "COMPLETED") {
    throw "Job did not complete successfully. Final status: $finalStatus"
}

$outFile = Join-Path $PSScriptRoot "speech-test.wav"
Write-Host "Downloading WAV to $outFile ..."
Invoke-WebRequest -Uri "$baseUrl/tts/jobs/$jobId/audio" -Method GET -OutFile $outFile

if (-not (Test-Path $outFile)) {
    throw "Expected output file not found: $outFile"
}

$size = (Get-Item $outFile).Length
Write-Host "Success. WAV bytes: $size"
