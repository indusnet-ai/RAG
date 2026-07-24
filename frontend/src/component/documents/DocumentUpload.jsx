// DocumentUpload.jsx
import React, { useState, useRef } from "react";
import { Upload, AlertCircle, CheckCircle, RefreshCw } from "lucide-react";
import api from "../../services/api";

const DocumentUpload = React.forwardRef(({
  userId = localStorage.getItem('userId') || "55", 
  onUploadSuccess,
  collectionName
}, ref) => {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [uploadQueue, setUploadQueue] = useState([]); // Track multiple uploads
  const [currentFileIndex, setCurrentFileIndex] = useState(0);
  const [showLongProcessingMessage, setShowLongProcessingMessage] = useState(false);
  const inputRef = useRef();
  const processingTimerRef = useRef(null);
  // ADD THIS - expose the click function
  React.useImperativeHandle(ref, () => ({
    triggerFileSelect: () => {
      inputRef.current?.click();
    }
  }));

  const allowedTypes = [
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ];

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const onFileSelect = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
    }
  };

  const handleFiles = (files) => {
    // Convert FileList to Array
    const filesArray = Array.from(files);
    
    // Validate files
    const validFiles = [];
    let hasError = false;

    for (const file of filesArray) {
      // Validate file type
      if (!allowedTypes.includes(file.type)) {
        setError(`File ${file.name} is not allowed. Only PDF, TXT, and DOCX files are allowed.`);
        hasError = true;
        break;
      }

      // Validate file size (10MB)
      if (file.size > 10 * 1024 * 1024) {
        setError(`File ${file.name} is too large. Maximum file size is 10MB.`);
        hasError = true;
        break;
      }
      
      validFiles.push(file);
    }

    if (hasError) {
      return;
    }

    // Set upload queue
    setUploadQueue(validFiles);
    
    // Start uploading files
    uploadFiles(validFiles);
  };

  const uploadFiles = async (files) => {
  setError(null);
  setSuccess(false);
  setUploading(true);
  setProgress(0);
  setCurrentFileIndex(0);
  setShowLongProcessingMessage(false);

  // Set timer to show message after 1 minutes
  processingTimerRef.current = setTimeout(() => {
    setShowLongProcessingMessage(true);
  }, 60000); // 1 minutes

  try {
      // Upload files one by one
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        setCurrentFileIndex(i);
        
        // Update progress based on current file
        const fileProgress = Math.round((i / files.length) * 100);
        setProgress(fileProgress);

        // Create FormData for each file
        const formData = new FormData();
        // Use collection name instead of user ID
        const actualCollectionName = collectionName || localStorage.getItem('collectionName');
        
        if (!actualCollectionName) {
          throw new Error("No collection name available for document upload");
        }
        
        if (actualCollectionName) {
          formData.append("collection_name", actualCollectionName);
        } else {
          formData.append("user_id", userId);
        }
        formData.append("files", file); // Field name must match backend

        // Track upload progress
        const response = await api.processFile(formData, (progressEvent) => {
          if (progressEvent.total) {
            // Calculate progress for current file (0-100%)
            const fileProgress = Math.round((progressEvent.loaded / progressEvent.total) * 100);
            
            // Calculate overall progress considering all files
            const previousFilesProgress = (i / files.length) * 100;
            const currentFileProgress = (fileProgress / 100) * (100 / files.length);
            const totalProgress = Math.round(previousFilesProgress + currentFileProgress);
            
            setProgress(totalProgress);
          }
        });

        const documentObj = {
          id: response.document_id || `${Date.now()}-${i}`,
          filename: response.file_name || file.name,
          status: response.status === "success" ? "ready" : "processing",
          type: "file",
          size: file.size,
          pages: response.chunks_inserted || null,
          uploadedAt: new Date().toISOString(),
        };

        // Notify parent component for each successful upload
        if (onUploadSuccess) {
          onUploadSuccess(documentObj);
        }

        // Update progress
        const updatedProgress = Math.round(((i + 1) / files.length) * 100);
        setProgress(updatedProgress);
      }

      setSuccess(true);

      // Clear the timer
      if (processingTimerRef.current) {
        clearTimeout(processingTimerRef.current);
      }

      setTimeout(() => {
        setUploading(false);
        setProgress(0);
        setSuccess(false);
        setUploadQueue([]);
        setCurrentFileIndex(0);
        setShowLongProcessingMessage(false);
        // Reset file input
        if (inputRef.current) {
          inputRef.current.value = "";
        }
      }, 1500);
    } catch (err) {
    // Clear the timer on error
    if (processingTimerRef.current) {
      clearTimeout(processingTimerRef.current);
    }
    
    setError(err.message);
    setUploading(false);
    setProgress(0);
    setUploadQueue([]);
    setCurrentFileIndex(0);
    setShowLongProcessingMessage(false);
  }
  };

  // Function to retry upload after token expiration
  const handleRetry = () => {
    if (uploadQueue.length > 0) {
      uploadFiles(uploadQueue);
    } else if (inputRef.current && inputRef.current.files.length > 0) {
      handleFiles(inputRef.current.files);
    }
  };

  return (
    <div className="w-full">
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
          dragActive 
            ? "border-blue-500 bg-blue-50" 
            : "border-gray-300 hover:border-blue-400"
        } ${uploading ? "opacity-50 pointer-events-none" : ""}`}
      >
        <input
          type="file"
          ref={inputRef}
          onChange={onFileSelect}
          disabled={uploading}
          className="hidden"
          id="file-upload"
          accept=".pdf,.txt,.docx"
          multiple // Allow multiple file selection
        />

        <div 
          onClick={() => {
            if (!uploading) {
              inputRef.current?.click();
            }
          }}
          className={`cursor-pointer ${uploading ? "cursor-not-allowed" : ""}`}
        >
          <Upload 
            className={`mx-auto h-10 w-10 mb-2 ${
              success ? "text-green-500" : "text-gray-400"
            }`} 
          />
          <p className="text-sm text-gray-600 mb-1">
            {uploading 
              ? `Uploading file ${currentFileIndex + 1} of ${uploadQueue.length}...` 
              : success 
              ? "Upload successful!" 
              : dragActive 
              ? "Drop your files here" 
              : "Click to upload or drag and drop"
            }
          </p>
          {showLongProcessingMessage && uploading && (
            <p className="text-sm text-orange-600 font-medium mt-2">
              ⚠️ Your uploaded file is getting processed in the backend, please check again after sometime.
            </p>
          )}
          <p className="text-xs text-gray-500">
            PDF, TXT, DOCX (max 10MB each, multiple files allowed)
          </p>
        </div>

        {uploading && (
          <div className="mt-4">
            <div className="w-full bg-gray-200 rounded-full h-2 mb-2 overflow-hidden">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all duration-300 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-sm text-gray-600 font-medium">{progress}%</p>
            {uploadQueue.length > 1 && (
              <p className="text-xs text-gray-500 mt-1">
                Uploading {currentFileIndex + 1} of {uploadQueue.length} files...
              </p>
            )}
          </div>
        )}

        {success && !uploading && (
          <div className="mt-4 flex items-center justify-center text-green-600 text-sm">
            <CheckCircle className="h-4 w-4 mr-2" />
            All files uploaded successfully!
          </div>
        )}

        {error && !uploading && (
          <div className="mt-4">
            <div className="flex items-center justify-center text-red-600 text-sm">
              <AlertCircle className="h-4 w-4 mr-2" />
              {error}
            </div>
            {(error.includes("expired") || error.includes("Session")) && (
              <button
                onClick={handleRetry}
                className="mt-2 inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-blue-700 bg-blue-100 hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                <RefreshCw className="h-3 w-3 mr-1" />
                Retry Upload
              </button>
            )}
          </div>
        )}
      </div>
    </div>
   );
});

export default DocumentUpload;