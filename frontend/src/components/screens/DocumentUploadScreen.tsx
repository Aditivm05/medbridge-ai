import React, { useState } from 'react';
import { Upload, FileText, AlertCircle, ArrowLeft, ArrowRight, Sparkles, ShieldCheck } from 'lucide-react';
import { CaseData, DocumentData, LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { sampleSyntheticDocuments } from '../../services/mockData';
import { SimulationBadge } from '../common/SimulationBadge';

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
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const attachedDocs = currentCase.documents || [];

  // Simulated synthetic loaders
  const handleLoadSyntheticDoc = (key: 'cbc_pdf' | 'xray_jpg') => {
    setIsUploading(true);
    setErrorMessage(null);
    setUploadMessage(t.uploadingDoc);

    setTimeout(() => {
      const template = sampleSyntheticDocuments[key];
      const newDoc: DocumentData = {
        ...template,
        documentId: `doc_upload_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
        caseId: currentCase.caseId,
        uploadedAt: new Date().toISOString(),
      };

      onAttachDocument(newDoc);
      setIsUploading(false);
      setUploadMessage(null);
    }, 700);
  };

  // Mock file drop handler
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    const validExtensions = ['.pdf', '.jpg', '.jpeg', '.png'];
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();

    if (!validExtensions.includes(ext)) {
      setErrorMessage(`Invalid file format '${ext}'. Only PDF, JPG, and PNG are permitted.`);
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setErrorMessage('File size exceeds the 10 MB limit.');
      return;
    }

    if (attachedDocs.length >= 5) {
      setErrorMessage('Maximum of 5 documents permitted per case.');
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);
    setUploadMessage(t.uploadingDoc);

    setTimeout(() => {
      const newDoc: DocumentData = {
        documentId: `doc_usr_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
        caseId: currentCase.caseId,
        fileName: file.name,
        mimeType: file.type || 'application/pdf',
        sizeBytes: file.size,
        uploadedAt: new Date().toISOString(),
        magicBytesValidated: true,
        ocrStatus: 'processed',
        extractedText: `Extracted text from user document [Synthetic simulation]: ${file.name}`,
      };

      onAttachDocument(newDoc);
      setIsUploading(false);
      setUploadMessage(null);
    }, 800);
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-8 shadow-xs">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-100 mb-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 cursor-pointer"
              aria-label="Back"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
                {t.uploadScreenTitle}
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
                {t.uploadScreenSubtitle}
              </p>
            </div>
          </div>
          <SimulationBadge />
        </div>

        {/* Case Context Summary */}
        <div className="bg-slate-50 rounded-xl p-3.5 mb-6 border border-slate-200 text-xs text-slate-700">
          <div className="flex items-center justify-between mb-1">
            <span className="font-bold text-slate-900">Case #{currentCase.caseId.substring(0, 14)}</span>
            <span className="font-semibold uppercase tracking-wider text-brand-700">{currentCase.requestedUrgency}</span>
          </div>
          <div className="line-clamp-1 italic text-slate-600">"{currentCase.chiefComplaint}"</div>
        </div>

        {/* 1-Click Synthetic Sample Reports (High value for Hackathon Demos) */}
        <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-amber-900 flex items-center gap-1.5 uppercase tracking-wide">
              <Sparkles className="w-3.5 h-3.5 text-amber-600" />
              {t.loadSyntheticReportTitle}
            </span>
            <SimulationBadge size="sm" />
          </div>
          <p className="text-xs text-amber-800 mb-3 leading-relaxed">
            Quickly attach pre-verified synthetic medical reports for instant AI extraction demonstration without uploading private files:
          </p>
          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              onClick={() => handleLoadSyntheticDoc('cbc_pdf')}
              disabled={isUploading || attachedDocs.length >= 5}
              className="px-3.5 py-2 rounded-lg bg-white border border-amber-300 hover:border-amber-400 hover:bg-amber-100/50 text-xs font-bold text-amber-950 shadow-2xs transition-all cursor-pointer disabled:opacity-50"
            >
              {t.loadSyntheticReportBtn}
            </button>
            <button
              type="button"
              onClick={() => handleLoadSyntheticDoc('xray_jpg')}
              disabled={isUploading || attachedDocs.length >= 5}
              className="px-3.5 py-2 rounded-lg bg-white border border-amber-300 hover:border-amber-400 hover:bg-amber-100/50 text-xs font-bold text-amber-950 shadow-2xs transition-all cursor-pointer disabled:opacity-50"
            >
              {t.loadSyntheticImagingBtn}
            </button>
          </div>
        </div>

        {/* Dropzone Area */}
        <div className="relative border-2 border-dashed border-slate-300 hover:border-brand-500 rounded-2xl p-6 sm:p-8 text-center bg-slate-50/50 transition-colors">
          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png"
            onChange={handleFileSelect}
            disabled={isUploading || attachedDocs.length >= 5}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
          />
          <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-brand-50 flex items-center justify-center text-brand-600 shadow-xs">
            <Upload className="w-6 h-6" />
          </div>
          <h3 className="text-sm sm:text-base font-bold text-slate-800 mb-1">
            {t.dropzoneTitle}
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {t.dropzoneHint}
          </p>

          <div className="mt-4 flex items-center justify-center gap-2 text-[11px] font-semibold text-teal-800 bg-teal-50 border border-teal-200 px-3 py-1 rounded-full w-fit mx-auto">
            <ShieldCheck className="w-3.5 h-3.5 text-teal-600" />
            <span>Private Cloud Storage • 15-Minute Short-Lived Signed URLs</span>
          </div>
        </div>

        {/* Upload Progress Status */}
        {isUploading && (
          <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-xl flex items-center gap-2 text-xs text-blue-800">
            <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin shrink-0" />
            <span className="font-semibold">{uploadMessage || t.uploadingDoc}</span>
          </div>
        )}

        {/* Error Notice */}
        {errorMessage && (
          <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-xl flex items-center gap-2 text-xs text-rose-800">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Uploaded Documents List */}
        <div className="mt-6">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
            {t.uploadedDocsCount} ({attachedDocs.length}/5)
          </h4>

          {attachedDocs.length === 0 ? (
            <p className="text-xs text-slate-400 italic">No reports attached yet. You can upload or proceed directly with symptom descriptions.</p>
          ) : (
            <div className="space-y-2">
              {attachedDocs.map((doc) => (
                <div
                  key={doc.documentId}
                  className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs"
                >
                  <div className="flex items-center gap-2.5">
                    <FileText className="w-4 h-4 text-brand-600 shrink-0" />
                    <div>
                      <span className="font-bold text-slate-800 block">{doc.fileName}</span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {(doc.sizeBytes / 1024).toFixed(1)} KB • {t.magicBytesVerified}
                      </span>
                    </div>
                  </div>

                  <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">
                    Validated
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Action Row */}
        <div className="flex items-center justify-between pt-6 border-t border-slate-100 mt-6">
          <button
            type="button"
            onClick={onBack}
            className="px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
          >
            Back
          </button>

          <button
            type="button"
            onClick={onProceedToBrief}
            disabled={isUploading}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-700 active:scale-95 text-white font-bold text-sm shadow-md shadow-brand-500/20 transition-all cursor-pointer"
          >
            <Sparkles className="w-4 h-4" />
            <span>{t.synthesizeBriefBtn}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
