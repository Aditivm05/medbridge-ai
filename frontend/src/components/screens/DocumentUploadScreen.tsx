import React, { useState, useRef } from 'react';
import {
  Upload,
  FileText,
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  RotateCcw,
  Trash2,
  Loader2,
  FileUp,
} from 'lucide-react';
import { CaseData, DocumentData, LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { sampleSyntheticDocuments } from '../../services/mockData';
import { SimulationBadge } from '../common/SimulationBadge';
import { api, mapUploadError } from '../../services/api';

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB
const MAX_DOCUMENTS_PER_CASE = 5;
const ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png'];

export type UploadStatus = 'Selected' | 'Uploading' | 'Confirmed by server' | 'Failed';

export interface UploadQueueItem {
  id: string;
  file: File;
  name: string;
  size: number;
  status: UploadStatus;
  progress: number;
  errorMessage?: string;
  serverDoc?: DocumentData;
}

interface DocumentUploadScreenProps {
  currentCase: CaseData;
  language: LanguageCode;
  onBack: () => void;
  onAttachDocument: (doc: DocumentData) => void;
  onProceedToBrief: () => void;
}

export const DocumentUploadScreen: React.FC<DocumentUploadScreenProps> = ({
  currentCase,
  language,
  onBack,
  onAttachDocument,
  onProceedToBrief,
}) => {
  const t = getTranslation(language);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // In-memory upload queue for files currently being managed (NEVER persisted to web storage)
  const [uploadQueue, setUploadQueue] = useState<UploadQueueItem[]>([]);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [syntheticLoading, setSyntheticLoading] = useState<string | null>(null);

  const attachedDocs = currentCase.documents || [];
  const isAnyUploading = uploadQueue.some((item) => item.status === 'Uploading') || syntheticLoading !== null;
  const hasSelectedFiles = uploadQueue.some((item) => item.status === 'Selected');
  const totalCount = attachedDocs.length;

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  // Process chosen files into the queue
  const handleFilesSelected = (files: FileList | File[]) => {
    setGlobalError(null);
    const newItems: UploadQueueItem[] = [];
    let currentTotal = attachedDocs.length + uploadQueue.filter((q) => q.status === 'Confirmed by server' || q.status === 'Selected' || q.status === 'Uploading').length;

    Array.from(files).forEach((file) => {
      const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
      const itemId = `queue_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;

      // Client-side UX checks (convenience only - server remains real gatekeeper)
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        newItems.push({
          id: itemId,
          file,
          name: file.name,
          size: file.size,
          status: 'Failed',
          progress: 0,
          errorMessage: 'Invalid file extension. Only PDF, JPG, and PNG documents are allowed.',
        });
        return;
      }

      if (file.size > MAX_FILE_SIZE_BYTES) {
        newItems.push({
          id: itemId,
          file,
          name: file.name,
          size: file.size,
          status: 'Failed',
          progress: 0,
          errorMessage: 'This file is larger than 10 MB.',
        });
        return;
      }

      if (currentTotal >= MAX_DOCUMENTS_PER_CASE) {
        newItems.push({
          id: itemId,
          file,
          name: file.name,
          size: file.size,
          status: 'Failed',
          progress: 0,
          errorMessage: 'Maximum 5 files per case reached.',
        });
        return;
      }

      currentTotal += 1;
      newItems.push({
        id: itemId,
        file,
        name: file.name,
        size: file.size,
        status: 'Selected',
        progress: 0,
      });
    });

    setUploadQueue((prev) => [...prev, ...newItems]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Upload a single queue item to the server with real progress tracking via XMLHttpRequest
  const uploadSingleItem = async (item: UploadQueueItem) => {
    // Transition status to Uploading
    setUploadQueue((prev) =>
      prev.map((q) => (q.id === item.id ? { ...q, status: 'Uploading', progress: 5, errorMessage: undefined } : q))
    );

    try {
      const confirmedDoc = await api.uploadDocument(currentCase.caseId, item.file, (percent) => {
        setUploadQueue((prev) =>
          prev.map((q) => (q.id === item.id ? { ...q, progress: Math.max(5, percent) } : q))
        );
      });

      // Update item to Confirmed by server
      setUploadQueue((prev) =>
        prev.map((q) =>
          q.id === item.id
            ? {
                ...q,
                status: 'Confirmed by server',
                progress: 100,
                serverDoc: confirmedDoc,
              }
            : q
        )
      );

      // Attach confirmed document to case store in memory
      onAttachDocument(confirmedDoc);
    } catch (err: any) {
      const friendlyMessage = mapUploadError(err.message || 'Upload failed');
      setUploadQueue((prev) =>
        prev.map((q) =>
          q.id === item.id
            ? {
                ...q,
                status: 'Failed',
                progress: 0,
                errorMessage: friendlyMessage,
              }
            : q
        )
      );
    }
  };

  // Trigger uploads for all currently 'Selected' files
  const handleUploadAllSelected = async () => {
    const selectedItems = uploadQueue.filter((q) => q.status === 'Selected');
    for (const item of selectedItems) {
      await uploadSingleItem(item);
    }
  };

  // Retry an individual failed file
  const handleRetryItem = async (item: UploadQueueItem) => {
    await uploadSingleItem(item);
  };

  // Remove an item from the queue
  const handleRemoveQueueItem = (id: string) => {
    setUploadQueue((prev) => prev.filter((q) => q.id !== id));
  };

  // Synthetic 1-click loaders from Phase 3 (strictly for simulated hackathon demonstrations)
  const handleLoadSyntheticDoc = (key: 'cbc_pdf' | 'xray_jpg') => {
    if (attachedDocs.length >= MAX_DOCUMENTS_PER_CASE) {
      setGlobalError('Maximum 5 files per case reached.');
      return;
    }

    setSyntheticLoading(key);
    setGlobalError(null);

    setTimeout(() => {
      const template = sampleSyntheticDocuments[key];
      const newDoc: DocumentData = {
        ...template,
        documentId: `doc_synth_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
        caseId: currentCase.caseId,
        uploadedAt: new Date().toISOString(),
      };

      onAttachDocument(newDoc);
      setSyntheticLoading(null);
    }, 600);
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto px-1 sm:px-0">
      <div className="bg-white rounded-2xl border border-slate-200 p-4 sm:p-8 shadow-xs">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 mb-6 gap-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              disabled={isAnyUploading}
              className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 cursor-pointer disabled:opacity-50 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500"
              aria-label="Back to intake screen"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h2 className="text-lg sm:text-2xl font-black text-slate-900 tracking-tight">
                {t.uploadScreenTitle}
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
                {t.uploadScreenSubtitle}
              </p>
            </div>
          </div>
          <div className="self-start sm:self-auto">
            <SimulationBadge />
          </div>
        </div>

        {/* Case Context Summary */}
        <div className="bg-slate-50 rounded-xl p-3.5 mb-6 border border-slate-200 text-xs text-slate-700">
          <div className="flex items-center justify-between mb-1">
            <span className="font-bold text-slate-900">Case #{currentCase.caseId.substring(0, 14)}</span>
            <span className="font-semibold uppercase tracking-wider text-brand-700">{currentCase.requestedUrgency}</span>
          </div>
          <div className="line-clamp-1 italic text-slate-600">"{currentCase.chiefComplaint}"</div>
        </div>

        {/* Synthetic Sample Reports (Demo presentation shortcut) */}
        <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-3.5 sm:p-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-amber-900 flex items-center gap-1.5 uppercase tracking-wide">
              <Sparkles className="w-3.5 h-3.5 text-amber-600" />
              {t.loadSyntheticReportTitle}
            </span>
            <SimulationBadge size="sm" label="DEMO / SIMULATED" />
          </div>
          <p className="text-xs text-amber-800 mb-3 leading-relaxed">
            Quickly attach pre-verified synthetic medical reports for instant demonstration without uploading private files:
          </p>
          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              onClick={() => handleLoadSyntheticDoc('cbc_pdf')}
              disabled={isAnyUploading || totalCount >= MAX_DOCUMENTS_PER_CASE}
              className="px-3 py-2 rounded-lg bg-white border border-amber-300 hover:border-amber-400 hover:bg-amber-100/50 text-xs font-bold text-amber-950 shadow-2xs transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-amber-500"
              aria-label="Load Synthetic CBC Blood Report (PDF)"
            >
              {syntheticLoading === 'cbc_pdf' ? (
                <span className="inline-flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-700" />
                  Loading...
                </span>
              ) : (
                t.loadSyntheticReportBtn
              )}
            </button>
            <button
              type="button"
              onClick={() => handleLoadSyntheticDoc('xray_jpg')}
              disabled={isAnyUploading || totalCount >= MAX_DOCUMENTS_PER_CASE}
              className="px-3 py-2 rounded-lg bg-white border border-amber-300 hover:border-amber-400 hover:bg-amber-100/50 text-xs font-bold text-amber-950 shadow-2xs transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-amber-500"
              aria-label="Load Synthetic Ultrasound Note (JPG)"
            >
              {syntheticLoading === 'xray_jpg' ? (
                <span className="inline-flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-700" />
                  Loading...
                </span>
              ) : (
                t.loadSyntheticImagingBtn
              )}
            </button>
          </div>
        </div>

        {/* Drag & Drop File Picker */}
        <div
          className={`relative border-2 border-dashed rounded-2xl p-5 sm:p-8 text-center transition-colors ${
            totalCount >= MAX_DOCUMENTS_PER_CASE
              ? 'border-slate-200 bg-slate-100/60 cursor-not-allowed'
              : 'border-slate-300 hover:border-brand-500 bg-slate-50/50'
          }`}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (isAnyUploading || totalCount >= MAX_DOCUMENTS_PER_CASE) return;
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
              handleFilesSelected(e.dataTransfer.files);
            }
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png"
            disabled={isAnyUploading || totalCount >= MAX_DOCUMENTS_PER_CASE}
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) {
                handleFilesSelected(e.target.files);
              }
            }}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
            aria-label="Select files to upload (PDF, JPG, PNG, max 10 MB)"
          />

          <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-brand-50 flex items-center justify-center text-brand-600 shadow-xs">
            <Upload className="w-6 h-6" />
          </div>

          <h3 className="text-sm sm:text-base font-bold text-slate-800 mb-1">
            {totalCount >= MAX_DOCUMENTS_PER_CASE
              ? 'Maximum 5 files per case reached'
              : t.dropzoneTitle}
          </h3>

          <p className="text-xs text-slate-500 max-w-sm mx-auto mb-3">
            {t.dropzoneHint}
          </p>

          <div className="flex flex-wrap items-center justify-center gap-2 text-[11px] font-semibold text-teal-800 bg-teal-50 border border-teal-200 px-3 py-1 rounded-full w-fit mx-auto">
            <ShieldCheck className="w-3.5 h-3.5 text-teal-600 shrink-0" />
            <span>Server Magic-Byte Validated • Max 10 MB per file • Max 5 files</span>
          </div>
        </div>

        {/* Global Error Notice */}
        {globalError && (
          <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-xl flex items-center gap-2 text-xs text-rose-800">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{globalError}</span>
          </div>
        )}

        {/* Upload Queue Section (Selected / Uploading / Failed files) */}
        {uploadQueue.length > 0 && (
          <div className="mt-6">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                <FileUp className="w-3.5 h-3.5 text-brand-600" />
                <span>Upload Queue ({uploadQueue.length})</span>
              </h4>

              {hasSelectedFiles && (
                <button
                  type="button"
                  onClick={handleUploadAllSelected}
                  disabled={isAnyUploading}
                  className="px-3.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 active:scale-95 text-white text-xs font-bold shadow-xs transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500"
                  aria-label="Upload all selected files"
                >
                  {isAnyUploading ? 'Uploading...' : 'Upload Selected Files'}
                </button>
              )}
            </div>

            <div className="space-y-2.5">
              {uploadQueue.map((item) => (
                <div
                  key={item.id}
                  className={`p-3.5 rounded-xl border transition-all ${
                    item.status === 'Confirmed by server'
                      ? 'bg-emerald-50/50 border-emerald-200'
                      : item.status === 'Failed'
                      ? 'bg-rose-50/50 border-rose-200'
                      : item.status === 'Uploading'
                      ? 'bg-blue-50/50 border-blue-200'
                      : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <FileText className="w-4 h-4 text-slate-500 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <span className="font-bold text-xs text-slate-900 truncate block">
                          {item.name}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          {formatFileSize(item.size)}
                        </span>
                      </div>
                    </div>

                    {/* Exact Status Badges */}
                    <div className="flex items-center gap-2 shrink-0">
                      {item.status === 'Selected' && (
                        <span className="text-[10px] sm:text-xs font-bold px-2 py-0.5 rounded-md bg-slate-200 text-slate-700 border border-slate-300">
                          Selected
                        </span>
                      )}

                      {item.status === 'Uploading' && (
                        <span className="inline-flex items-center gap-1 text-[10px] sm:text-xs font-bold px-2 py-0.5 rounded-md bg-blue-100 text-blue-800 border border-blue-200 animate-pulse">
                          <Loader2 className="w-3 h-3 animate-spin text-blue-600" />
                          Uploading ({item.progress}%)
                        </span>
                      )}

                      {item.status === 'Confirmed by server' && (
                        <span className="inline-flex items-center gap-1 text-[10px] sm:text-xs font-bold px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 border border-emerald-300">
                          <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                          Confirmed by server
                        </span>
                      )}

                      {item.status === 'Failed' && (
                        <span className="inline-flex items-center gap-1 text-[10px] sm:text-xs font-bold px-2 py-0.5 rounded-md bg-rose-100 text-rose-800 border border-rose-300">
                          <AlertCircle className="w-3 h-3 text-rose-600" />
                          Failed
                        </span>
                      )}

                      {/* Retry Button (strictly for Failed status only) */}
                      {item.status === 'Failed' && (
                        <button
                          type="button"
                          onClick={() => handleRetryItem(item)}
                          disabled={isAnyUploading}
                          className="inline-flex items-center gap-1 text-xs font-bold text-rose-700 hover:text-rose-900 bg-rose-100 hover:bg-rose-200 px-2 py-1 rounded-md border border-rose-300 transition-colors cursor-pointer disabled:opacity-50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-rose-500"
                          aria-label={`Retry upload for ${item.name}`}
                          title="Retry upload to server"
                        >
                          <RotateCcw className="w-3 h-3" />
                          <span>Retry</span>
                        </button>
                      )}

                      {/* Remove Button */}
                      {item.status !== 'Uploading' && (
                        <button
                          type="button"
                          onClick={() => handleRemoveQueueItem(item.id)}
                          className="p-1 text-slate-400 hover:text-slate-700 rounded-md transition-colors cursor-pointer focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-slate-400"
                          aria-label={`Remove ${item.name} from queue`}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Per-File Progress Bar (Active during Uploading or confirmed) */}
                  {(item.status === 'Uploading' || item.status === 'Confirmed by server') && (
                    <div className="w-full mt-2">
                      <div
                        role="progressbar"
                        aria-valuenow={item.progress}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`Upload progress for ${item.name}`}
                        className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden"
                      >
                        <div
                          className={`h-full transition-all duration-300 rounded-full ${
                            item.status === 'Confirmed by server' ? 'bg-emerald-600' : 'bg-brand-600'
                          }`}
                          style={{ width: `${item.progress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Error Message for Failed Items */}
                  {item.status === 'Failed' && item.errorMessage && (
                    <div className="mt-2 text-[11px] text-rose-700 flex items-start gap-1 font-medium bg-rose-100/60 p-2 rounded-lg border border-rose-200">
                      <AlertCircle className="w-3.5 h-3.5 text-rose-600 shrink-0 mt-0.5" />
                      <span>{item.errorMessage}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Attached Documents List (Confirmed & attached to case) */}
        <div className="mt-6">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
              {t.uploadedDocsCount} ({attachedDocs.length}/5)
            </h4>
            <span className="text-[11px] text-slate-500 font-medium">
              {5 - attachedDocs.length} remaining slots
            </span>
          </div>

          {attachedDocs.length === 0 ? (
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center text-xs text-slate-500 italic">
              No reports attached yet. You can attach synthetic demo reports above, upload your own, or proceed directly.
            </div>
          ) : (
            <div className="space-y-2">
              {attachedDocs.map((doc) => (
                <div
                  key={doc.documentId}
                  className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs"
                >
                  <div className="flex items-center gap-2.5 min-w-0 flex-1">
                    <FileText className="w-4 h-4 text-brand-600 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <span className="font-bold text-slate-800 truncate block">{doc.fileName}</span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {formatFileSize(doc.sizeBytes)} • {t.magicBytesVerified}
                      </span>
                    </div>
                  </div>

                  <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-100 border border-emerald-200 px-2 py-0.5 rounded-md shrink-0">
                    Confirmed
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Action Row */}
        <div className="flex items-center justify-between pt-6 border-t border-slate-100 mt-6 gap-3">
          <button
            type="button"
            onClick={onBack}
            disabled={isAnyUploading}
            className="px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-800 cursor-pointer disabled:opacity-50 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500"
            aria-label="Return to intake screen"
          >
            Back
          </button>

          <button
            type="button"
            onClick={onProceedToBrief}
            disabled={isAnyUploading}
            className="inline-flex items-center gap-2 px-5 sm:px-6 py-2.5 sm:py-3 rounded-xl bg-brand-600 hover:bg-brand-700 active:scale-95 text-white font-bold text-xs sm:text-sm shadow-md shadow-brand-500/20 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500"
            aria-label="Generate AI Doctor Brief from attached documents"
          >
            {isAnyUploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-white" />
                <span>Uploading...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>{t.synthesizeBriefBtn}</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
