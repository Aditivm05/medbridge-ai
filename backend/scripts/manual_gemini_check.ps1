<#
================================================================================
SYNTHETIC DATA ONLY - STRICTLY FOR LOCAL DEVELOPMENT AND LIVE VERIFICATION
MedBridge AI: Live Gemini Multimodal OCR & AI Doctor Brief Verification
================================================================================
Notice:
- This script uses ONLY synthetic patient personas and sample medical scans.
- NEVER input real Protected Health Information (PHI) or Personally Identifiable Information (PII).
- Reads NO secrets or API keys and NEVER prints any API keys or credentials.
- Interacts strictly with local Firebase emulators and the MedBridge AI backend server.
================================================================================
#>

[CmdletBinding()]
param (
    [Parameter(Mandatory = $true, HelpMessage = "Path to sample medical scan or report (PDF, PNG, JPG)")]
    [ValidateNotNullOrEmpty()]
    [string]$ScanPath,

    [Parameter(Mandatory = $false, HelpMessage = "Base URL of MedBridge AI FastAPI backend")]
    [string]$BackendUrl = "http://127.0.0.1:8000",

    [Parameter(Mandatory = $false, HelpMessage = "URL of Firebase Auth Emulator")]
    [string]$AuthEmulatorUrl = "http://127.0.0.1:9099"
)

$ErrorActionPreference = "Stop"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  MedBridge AI - Live Gemini Multimodal OCR & Doctor Brief Check" -ForegroundColor Cyan
Write-Host "  [SYNTHETIC DATA ONLY - LOCAL DEV & EMULATOR VERIFICATION]" -ForegroundColor Yellow
Write-Host "================================================================================" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# 0. Validate Input File
# ------------------------------------------------------------------------------
if (-not (Test-Path -Path $ScanPath -PathType Leaf)) {
    Write-Error "Scan file not found at path: '$ScanPath'. Please provide a valid file path."
    exit 1
}

$fileItem = Get-Item -Path $ScanPath
$resolvedPath = $fileItem.FullName
$fileExt = $fileItem.Extension.ToLower()

$mimeType = switch ($fileExt) {
    ".pdf"  { "application/pdf" }
    ".jpg"  { "image/jpeg" }
    ".jpeg" { "image/jpeg" }
    ".png"  { "image/png" }
    Default {
        Write-Error "Unsupported file extension '$fileExt'. Allowed extensions: .pdf, .jpg, .jpeg, .png"
        exit 1
    }
}

Write-Host "[0/6] Verified local sample scan file: $($fileItem.Name) ($([math]::Round($fileItem.Length / 1KB, 2)) KB, MIME: $mimeType)" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 1. Sign Up Synthetic Patient in Firebase Auth Emulator
# ------------------------------------------------------------------------------
$timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$syntheticEmail = "synthetic.patient.$timestamp@example.com"
$syntheticPassword = "SyntheticPassword123!"

Write-Host "[1/6] Registering synthetic patient in Auth emulator ($syntheticEmail)..." -ForegroundColor Cyan

$signUpEndpoint = "$AuthEmulatorUrl/identitytoolkit.googleapis.com/v1/accounts:signUp?key=fake-api-key"
$signUpBody = @{
    email             = $syntheticEmail
    password          = $syntheticPassword
    returnSecureToken = $true
} | ConvertTo-Json

try {
    $authRes = Invoke-RestMethod -Uri $signUpEndpoint -Method Post -Body $signUpBody -ContentType "application/json"
    $idToken = $authRes.idToken
    $patientUid = $authRes.localId
    Write-Host "      -> Synthetic patient registered successfully: UID = $patientUid" -ForegroundColor Green
}
catch {
    Write-Error "Failed to sign up synthetic patient on Auth Emulator at $AuthEmulatorUrl. Is the Firebase emulator running? Details: $_"
    exit 1
}

$headers = @{
    "Authorization" = "Bearer $idToken"
    "Content-Type"  = "application/json"
}

# ------------------------------------------------------------------------------
# 2. Create Case via Backend API
# ------------------------------------------------------------------------------
Write-Host "[2/6] Creating urgent care consultation case..." -ForegroundColor Cyan

$idempotencyKey = [guid]::NewGuid().ToString()
$caseCreateBody = @{
    chiefComplaint   = "Severe right lower quadrant abdominal pain and nausea for 2 days"
    duration         = "2 days"
    requestedUrgency = "urgent"
    patientLanguage  = "en"
    idempotencyKey   = $idempotencyKey
} | ConvertTo-Json

try {
    $caseRes = Invoke-RestMethod -Uri "$BackendUrl/api/v1/cases" -Method Post -Headers $headers -Body $caseCreateBody
    $caseId = $caseRes.caseId
    Write-Host "      -> Case created successfully: ID = $caseId (Status = $($caseRes.status), Urgency = $($caseRes.requestedUrgency))" -ForegroundColor Green
}
catch {
    Write-Error "Failed to create case at $BackendUrl/api/v1/cases. Is the backend server running? Details: $_"
    exit 1
}

# ------------------------------------------------------------------------------
# 3. Save History / Medications / Allergies / Vitals via Real Metadata Keys
# ------------------------------------------------------------------------------
Write-Host "[3/6] Saving clinical intake metadata (history, medications, allergies, vitals)..." -ForegroundColor Cyan

$metadataPatchBody = @{
    metadata = @{
        symptoms        = @(
            "acute right lower quadrant pain with rebound tenderness",
            "persistent nausea without emesis",
            "loss of appetite"
        )
        knownConditions = "Mild exercise-induced asthma (diagnosed 2021)"
        medications     = "Albuterol inhaler 90mcg as needed (last used 2 weeks ago)"
        allergies       = "Amoxicillin (resulted in generalized hives in 2018)"
        vitals          = @{
            bloodPressure   = "122/80 mmHg"
            heartRate       = "88 bpm"
            temperature     = "100.2 F"
            respiratoryRate = "18 breaths/min"
            spo2            = "98%"
        }
    }
} | ConvertTo-Json -Depth 5

try {
    $patchRes = Invoke-RestMethod -Uri "$BackendUrl/api/v1/cases/$caseId" -Method Patch -Headers $headers -Body $metadataPatchBody
    Write-Host "      -> Clinical metadata saved successfully (Case Version = $($patchRes.version))" -ForegroundColor Green
}
catch {
    Write-Error "Failed to save clinical intake metadata. Details: $_"
    exit 1
}

# ------------------------------------------------------------------------------
# 4. Upload Document Scan via Multipart Direct Upload
# ------------------------------------------------------------------------------
Write-Host "[4/6] Uploading sample medical scan ($($fileItem.Name))..." -ForegroundColor Cyan

$uploadEndpoint = "$BackendUrl/api/v1/cases/$caseId/documents/upload-and-verify"

# Using curl.exe for reliable cross-version multipart form handling in Windows PowerShell
$curlOutput = & curl.exe -s -w "`n%{http_code}" -X POST `
    -H "Authorization: Bearer $idToken" `
    -F "file=@$resolvedPath;type=$mimeType" `
    "$uploadEndpoint"

$curlLines = $curlOutput -split "`n"
$httpStatus = $curlLines[-1].Trim()
$jsonBody = ($curlLines[0..($curlLines.Length - 2)] -join "`n").Trim()

if ($httpStatus -ne "200" -and $httpStatus -ne "201") {
    Write-Error "Document upload failed with HTTP status $httpStatus. Response: $jsonBody"
    exit 1
}

$docRes = $jsonBody | ConvertFrom-Json
$documentId = $docRes.documentId
Write-Host "      -> Document uploaded and verified: ID = $documentId (Status = $($docRes.extractionStatus))" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 5. Poll Document until EXTRACTED or FAILED
# ------------------------------------------------------------------------------
Write-Host "[5/6] Polling document extraction status..." -ForegroundColor Cyan

$maxAttempts = 30
$delaySeconds = 2
$finalDoc = $null
$ocrTriggered = $false

for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    Start-Sleep -Seconds $delaySeconds
    $currentDoc = Invoke-RestMethod -Uri "$BackendUrl/api/v1/cases/$caseId/documents/$documentId" -Method Get -Headers $headers

    Write-Host "      [Attempt $attempt/$maxAttempts] Extraction Status: $($currentDoc.extractionStatus), OCR Status: $($currentDoc.ocrStatus)" -ForegroundColor DarkGray

    # If extraction found low text / scanned format and flagged NEEDS_OCR, trigger Gemini OCR
    if ($currentDoc.extractionStatus -eq "NEEDS_OCR" -and -not $ocrTriggered) {
        Write-Host "      -> Document flagged NEEDS_OCR. Triggering Gemini Multimodal OCR..." -ForegroundColor Magenta
        try {
            $ocrRes = Invoke-RestMethod -Uri "$BackendUrl/api/v1/cases/$caseId/documents/$documentId/ocr" -Method Post -Headers $headers
            $ocrTriggered = $true
            Write-Host "      -> Gemini OCR triggered successfully. Extraction status: $($ocrRes.extractionStatus)" -ForegroundColor Magenta
        }
        catch {
            $errDetail = if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $_.ErrorDetails.Message } else { $_.Exception.Message }
            Write-Warning "Failed to trigger OCR: $errDetail"
        }
    }

    if ($currentDoc.extractionStatus -eq "EXTRACTED" -or $currentDoc.extractionStatus -eq "FAILED") {
        $finalDoc = $currentDoc
        break
    }
}

if (-not $finalDoc) {
    Write-Error "Document extraction timed out after $($maxAttempts * $delaySeconds) seconds."
    exit 1
}

Write-Host "      -> Final Document Status: $($finalDoc.extractionStatus)" -ForegroundColor $(if ($finalDoc.extractionStatus -eq "EXTRACTED") { "Green" } else { "Red" })

# Fetch per-page extracted text
Write-Host "`n--------------------------------------------------------------------------------" -ForegroundColor DarkCyan
Write-Host "  DOCUMENT EXTRACTED PAGES" -ForegroundColor DarkCyan
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor DarkCyan

try {
    $textRes = Invoke-RestMethod -Uri "$BackendUrl/api/v1/cases/$caseId/documents/$documentId/text" -Method Get -Headers $headers
    if ($textRes.pages -and $textRes.pages.Count -gt 0) {
        foreach ($pg in $textRes.pages) {
            Write-Host "`n[Page $($pg.pageNumber)] Source: $($pg.source) | CharCount: $($pg.charCount)" -ForegroundColor Yellow
            Write-Host $pg.text -ForegroundColor Gray
        }
    } else {
        Write-Host "No pages extracted or text unavailable. FullText: $($textRes.fullText)" -ForegroundColor Gray
    }
}
catch {
    Write-Warning "Could not fetch document text details: $_"
}

# ------------------------------------------------------------------------------
# 6. Generate AI Doctor Brief and Print Output
# ------------------------------------------------------------------------------
Write-Host "`n[6/6] Generating AI Doctor Brief (POST /cases/$caseId/brief/generate)..." -ForegroundColor Cyan

$generateBody = @{
    confirmRegenerate = $false
} | ConvertTo-Json

try {
    $brief = Invoke-RestMethod -Uri "$BackendUrl/api/v1/cases/$caseId/brief/generate" -Method Post -Headers $headers -Body $generateBody

    Write-Host "      -> AI Doctor Brief generated successfully: ID = $($brief.briefId), Version = $($brief.version)" -ForegroundColor Green

    Write-Host "`n================================================================================" -ForegroundColor Cyan
    Write-Host "  AI DOCTOR BRIEF SUMMARY (CLINICAL SAFETY COORDINATION)" -ForegroundColor Cyan
    Write-Host "================================================================================" -ForegroundColor Cyan

    Write-Host "Brief ID:               $($brief.briefId)" -ForegroundColor White
    Write-Host "Schema Version:         $($brief.schemaVersion)" -ForegroundColor White
    Write-Host "Status:                 $($brief.briefStatus)" -ForegroundColor White
    Write-Host "Version Counter:        $($brief.version)" -ForegroundColor White
    Write-Host "Disclaimer:             $($brief.disclaimer)" -ForegroundColor DarkYellow

    Write-Host "`n--- REASON FOR CONSULTATION (Verbatim Patient Complaint) ---" -ForegroundColor Yellow
    Write-Host $brief.reasonForConsultation -ForegroundColor White

    Write-Host "`n--- TIMELINE & DETAILS ---" -ForegroundColor Yellow
    Write-Host "Timeline & Details:     $($brief.timelineAndDetails)" -ForegroundColor White

    Write-Host "`n--- RELEVANT HISTORY ---" -ForegroundColor Yellow
    if ($brief.relevantHistory -and $brief.relevantHistory.Count -gt 0) {
        $brief.relevantHistory | Format-Table -Property fact, source, reference -AutoSize
    } else {
        Write-Host "(None reported)" -ForegroundColor Gray
    }

    Write-Host "`n--- CURRENT MEDICATIONS ---" -ForegroundColor Yellow
    if ($brief.currentMedications -and $brief.currentMedications.Count -gt 0) {
        $brief.currentMedications | Format-Table -Property fact, source, reference -AutoSize
    } else {
        Write-Host "(None reported)" -ForegroundColor Gray
    }

    Write-Host "`n--- REPORTED ALLERGIES ---" -ForegroundColor Yellow
    if ($brief.patientReportedAllergies -and $brief.patientReportedAllergies.Count -gt 0) {
        $brief.patientReportedAllergies | Format-Table -Property fact, source, reference -AutoSize
    } else {
        Write-Host "(None reported)" -ForegroundColor Gray
    }

    Write-Host "`n--- REPORTED VITALS ---" -ForegroundColor Yellow
    if ($brief.vitals -and $brief.vitals.Count -gt 0) {
        $brief.vitals | Format-Table -Property name, value, unit, source -AutoSize
    } else {
        Write-Host "(No vitals reported)" -ForegroundColor Gray
    }

    Write-Host "`n--- DOCUMENT FINDINGS ---" -ForegroundColor Yellow
    if ($brief.documentFindings -and $brief.documentFindings.Count -gt 0) {
        $brief.documentFindings | Format-Table -Property finding, documentId, pageNumber, extractionSource -AutoSize
    } else {
        Write-Host "(No document findings extracted)" -ForegroundColor Gray
    }

    Write-Host "`n--- CLINICAL CONFLICTS IDENTIFIED ---" -ForegroundColor Yellow
    if ($brief.conflicts -and $brief.conflicts.Count -gt 0) {
        $brief.conflicts | Format-Table -Property item, valueA, sourceA, valueB, sourceB -AutoSize
    } else {
        Write-Host "(None identified)" -ForegroundColor Gray
    }

    Write-Host "`n--- MISSING INFORMATION ---" -ForegroundColor Yellow
    if ($brief.missingInformation -and $brief.missingInformation.Count -gt 0) {
        foreach ($item in $brief.missingInformation) {
            Write-Host " - $item" -ForegroundColor White
        }
    } else {
        Write-Host "(None)" -ForegroundColor Gray
    }

    Write-Host "`n--- CLARIFICATION QUESTIONS FOR CLINICIAN ---" -ForegroundColor Yellow
    if ($brief.clarificationQuestions -and $brief.clarificationQuestions.Count -gt 0) {
        foreach ($q in $brief.clarificationQuestions) {
            Write-Host " - $q" -ForegroundColor White
        }
    } else {
        Write-Host "(None)" -ForegroundColor Gray
    }

    if ($brief.validationWarnings -and $brief.validationWarnings.Count -gt 0) {
        Write-Host "`n--- VALIDATION WARNINGS ---" -ForegroundColor Red
        foreach ($w in $brief.validationWarnings) {
            Write-Host " [!] $w" -ForegroundColor Red
        }
    }

    Write-Host "`n--------------------------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "  RAW DOCTOR BRIEF JSON (STRUCTURED OUTPUT)" -ForegroundColor DarkGray
    Write-Host "--------------------------------------------------------------------------------" -ForegroundColor DarkGray
    $brief | ConvertTo-Json -Depth 10 | Write-Host -ForegroundColor Gray

}
catch {
    Write-Error "Failed to generate AI Doctor Brief. Details: $_"
    exit 1
}

# ------------------------------------------------------------------------------
# 7. Final Verification Evaluation & Failure Summary
# ------------------------------------------------------------------------------
$failures = @()

if (-not $finalDoc -or $finalDoc.extractionStatus -ne "EXTRACTED") {
    $docStatus = if ($finalDoc) { $finalDoc.extractionStatus } else { "TIMEOUT" }
    $docErr = if ($finalDoc -and $finalDoc.errorMessage) { " ($($finalDoc.errorMessage))" } else { "" }
    $failures += "Document OCR / extraction failed or did not reach EXTRACTED status (Status: $docStatus)$docErr"
}

if ($brief) {
    if ($brief.validationWarnings) {
        foreach ($w in $brief.validationWarnings) {
            if ($w -match "AI generation failed" -or $w -match "AI brief generation unavailable") {
                $failures += "Doctor Brief fell back to skeleton due to AI generation warning: $w"
            }
        }
    }
    if ($brief.missingInformation) {
        foreach ($m in $brief.missingInformation) {
            if ($m -match "AI brief generation unavailable or failed") {
                if (-not ($failures -match "AI brief generation unavailable or failed")) {
                    $failures += "Doctor Brief fell back to skeleton: $m"
                }
            }
        }
    }
}

if ($failures.Count -gt 0) {
    Write-Host "`n================================================================================" -ForegroundColor Red
    Write-Host "  FAIL / WARN SUMMARY" -ForegroundColor Red
    Write-Host "================================================================================" -ForegroundColor Red
    foreach ($f in $failures) {
        Write-Host " [FAIL] $f" -ForegroundColor Red
    }
    Write-Host "`nLive verification failed. Exiting with non-zero status code." -ForegroundColor Red
    exit 1
}

Write-Host "`n================================================================================" -ForegroundColor Green
Write-Host "  Live verification workflow completed successfully." -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green
