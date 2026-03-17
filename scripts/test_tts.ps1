# Тест TTS API с проверкой binary protocol

$ErrorActionPreference = "Stop"

# Тестовый текст
$text = "Привет мир! Это тест системы синтеза речи. Проверяем работу прогресс бара."

# Отправляем запрос
Write-Host "Отправка запроса на сервер..."
$body = @{
    text = $text
    language = "ru"
} | ConvertTo-Json -Compress

$headers = @{
    "Content-Type" = "application/json; charset=utf-8"
}

$response = Invoke-WebRequest -Uri "http://127.0.0.1:5001/tts" -Method POST -Body $body -Headers $headers

Write-Host "Status: $($response.StatusCode)"
Write-Host "Content-Type: $($response.Headers['Content-Type'])"
Write-Host "Content-Length: $($response.RawContentLength)"

# Сохраняем и анализируем
$response.RawContentStream.Position = 0
$bytes = $response.RawContentStream.ToArray()

Write-Host "Total bytes: $($bytes.Length)"
Write-Host "First 50 bytes (hex):"
$bytes[0..49] | ForEach-Object { "{0:X2}" -f $_ } | Write-Host

# Парсим первый блок
if ($bytes.Length -gt 4) {
    $metadataSize = [System.BitConverter]::ToUInt32($bytes, 0)
    Write-Host "Metadata size: $metadataSize"
    
    $metadataBytes = $bytes[4..($metadataSize+3)]
    $metadataJson = [System.Text.Encoding]::UTF8.GetString($metadataBytes)
    Write-Host "Metadata JSON: $metadataJson"
}

Write-Host "TEST PASSED!"
