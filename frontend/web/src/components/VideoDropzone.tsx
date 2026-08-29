import React, { useState, useRef } from 'react';
import { uploadVideo, type UploadResponse } from '@/api/ingest';
import { useNavigate } from 'react-router-dom';

interface VideoDropzoneProps {
  onSuccess?: (res: UploadResponse) => void;
}

export function VideoDropzone({ onSuccess }: VideoDropzoneProps) {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [missionName, setMissionName] = useState('');
  const [preset, setPreset] = useState('standard');
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [bytesUploaded, setBytesUploaded] = useState(0);
  const [totalBytes, setTotalBytes] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successResult, setSuccessResult] = useState<UploadResponse | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile) validateAndSetFile(droppedFile);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      if (selectedFile) validateAndSetFile(selectedFile);
    }
  };

  const validateAndSetFile = (f: File) => {
    if (!f.type.startsWith('video/') && !/\.(mp4|mov|avi|mkv|webm)$/i.test(f.name)) {
      setErrorMsg('Please select a valid video file (.mp4, .mov, .avi, .mkv)');
      return;
    }
    setErrorMsg(null);
    setFile(f);
    if (!missionName) {
      setMissionName(f.name.replace(/\.[^/.]+$/, ''));
    }
  };

  const handleStartUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setErrorMsg(null);
    setUploadProgress(0);

    try {
      const res = await uploadVideo(
        file,
        missionName || undefined,
        preset,
        (pct, loaded, total) => {
          setUploadProgress(pct);
          setBytesUploaded(loaded);
          setTotalBytes(total);
        }
      );
      setSuccessResult(res);
      if (onSuccess) {
        onSuccess(res);
      }
    } catch (err) {
      setErrorMsg((err as Error).message || 'Failed to upload video');
    } finally {
      setIsUploading(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const resetForm = () => {
    setFile(null);
    setMissionName('');
    setPreset('standard');
    setUploadProgress(0);
    setErrorMsg(null);
    setSuccessResult(null);
  };

  return (
    <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-800 mb-1">Upload Drone Video</h2>
      <p className="text-sm text-slate-500 mb-4">
        Drag and drop a single-pass drone video to initiate automated 3D reconstruction.
      </p>

      {successResult ? (
        <div className="rounded-lg bg-emerald-50 p-4 border border-emerald-200">
          <div className="flex items-center space-x-2 text-emerald-800 font-semibold mb-2">
            <svg className="w-5 h-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>Video Uploaded & Pipeline Launched!</span>
          </div>
          <p className="text-sm text-emerald-700 mb-3">{successResult.message}</p>
          <div className="text-xs text-slate-600 space-y-1 mb-4">
            <div><span className="font-mono text-slate-500">Mission ID:</span> {successResult.mission_id}</div>
            <div><span className="font-mono text-slate-500">Workflow ID:</span> {successResult.temporal_workflow_id}</div>
          </div>
          <div className="flex space-x-3">
            <button
              onClick={() => navigate(`/missions/${successResult.mission_id}`)}
              className="px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white font-medium text-sm rounded-lg shadow-sm"
            >
              View Mission Reconstruction
            </button>
            <button
              onClick={resetForm}
              className="px-4 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 font-medium text-sm rounded-lg shadow-sm"
            >
              Upload Another Video
            </button>
          </div>
        </div>
      ) : (
        <>
          {!file ? (
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative cursor-pointer flex flex-col items-center justify-center p-8 rounded-xl border-2 border-dashed transition-all ${
                isDragging
                  ? 'border-sky-500 bg-sky-50/50'
                  : 'border-slate-300 hover:border-slate-400 bg-slate-50/50'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*,.mp4,.mov,.avi,.mkv"
                onChange={handleFileSelect}
                className="hidden"
              />
              <div className="w-12 h-12 mb-3 text-sky-600 bg-sky-100 rounded-full flex items-center justify-center">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <p className="text-slate-700 font-medium text-sm">
                <span className="text-sky-600 font-semibold">Click to select video</span> or drag and drop here
              </p>
              <p className="text-slate-400 text-xs mt-1">MP4, MOV, AVI, MKV up to 8GB</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-200">
                <div className="flex items-center space-x-3 truncate">
                  <div className="w-10 h-10 text-sky-600 bg-sky-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <div className="truncate">
                    <p className="text-sm font-medium text-slate-800 truncate">{file.name}</p>
                    <p className="text-xs text-slate-500">{formatSize(file.size)}</p>
                  </div>
                </div>
                {!isUploading && (
                  <button
                    onClick={resetForm}
                    className="text-slate-400 hover:text-red-500 p-1 transition-colors"
                    title="Remove file"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Mission Name
                  </label>
                  <input
                    type="text"
                    value={missionName}
                    onChange={(e) => setMissionName(e.target.value)}
                    disabled={isUploading}
                    placeholder="e.g. Flight-Pass-Alpha"
                    className="w-full text-sm px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Reconstruction Quality Preset
                  </label>
                  <select
                    value={preset}
                    onChange={(e) => setPreset(e.target.value)}
                    disabled={isUploading}
                    className="w-full text-sm px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 bg-white disabled:bg-slate-100"
                  >
                    <option value="standard">Standard (Balanced 3DGS & Mesh)</option>
                    <option value="fast_tsdf">Fast Draft (Real-time TSDF)</option>
                    <option value="survey_3dgs">Survey Grade (High-Precision 3DGS)</option>
                  </select>
                </div>
              </div>

              {isUploading && (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-slate-600">
                    <span>Uploading video… {uploadProgress}%</span>
                    <span>{formatSize(bytesUploaded)} / {formatSize(totalBytes)}</span>
                  </div>
                  <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-sky-600 h-2 rounded-full transition-all duration-200"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}

              {errorMsg && (
                <div className="p-3 text-xs bg-red-50 text-red-700 rounded-lg border border-red-200">
                  {errorMsg}
                </div>
              )}

              <div className="flex justify-end space-x-3 pt-2">
                <button
                  onClick={resetForm}
                  disabled={isUploading}
                  className="px-4 py-2 border border-slate-300 text-slate-700 font-medium text-sm rounded-lg hover:bg-slate-50 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleStartUpload}
                  disabled={isUploading}
                  className="px-5 py-2 bg-sky-600 hover:bg-sky-700 text-white font-medium text-sm rounded-lg shadow-sm disabled:opacity-50 flex items-center space-x-2"
                >
                  {isUploading ? (
                    <>
                      <svg className="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      <span>Uploading…</span>
                    </>
                  ) : (
                    <span>Start 3D Reconstruction</span>
                  )}
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
