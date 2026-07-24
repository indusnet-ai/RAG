import React, { useState, useEffect } from "react";
import { HardDrive, AlertCircle, CheckCircle, Loader, HelpCircle, Link as LinkIcon, FolderOpen, AlertTriangle, Info, RefreshCw } from "lucide-react";
import api from "../../services/api";

const GoogleDriveInput = ({ userId = "55", onAddSuccess, collectionName }) => {
  const [driveUrl, setDriveUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [isPickerLoaded, setIsPickerLoaded] = useState(false);
  const [pickerError, setPickerError] = useState(false);

  // Load Google Drive Picker API
  useEffect(() => {
    const loadGoogleDrivePicker = () => {
      if (window.google && window.google.picker) {
        setIsPickerLoaded(true);
        return;
      }

      // Create script tag for Google Picker API
      const script = document.createElement('script');
      script.src = "https://apis.google.com/js/api.js";
      script.onload = () => {
        window.gapi.load('picker', () => {
          setIsPickerLoaded(true);
        });
      };
      script.onerror = () => {
        console.warn('Failed to load Google Drive Picker API');
        setPickerError(true);
      };
      document.head.appendChild(script);
    };

    // Only load if not already loaded
    if (!isPickerLoaded) {
      loadGoogleDrivePicker();
    }
  }, [isPickerLoaded]);

  const validateDriveUrl = (string) => {
    try {
      const url = new URL(string);
      return url.hostname.includes("drive.google.com") || url.hostname.includes("docs.google.com");
    } catch (_) {
      return false;
    }
  };

  // Create and show Google Drive Picker
  const showGoogleDrivePicker = () => {
    if (!isPickerLoaded) {
      setError("Google Drive Picker is still loading. Please try again.");
      return;
    }

    try {
      // Create picker for publicly shared files
      // Note: This will only work with properly shared files and valid API credentials
      const picker = new window.google.picker.PickerBuilder()
        .addView(window.google.picker.ViewId.DOCS)
        .setDeveloperKey("AIzaSyCrZzN5c7ZYg8vncvD1G1iQfTzX3Nf6N4Y") // Placeholder - requires proper setup
        .setCallback(pickerCallback)
        .setTitle("Select a Google Drive file")
        .setSize(800, 600)
        .build();
      
      picker.setVisible(true);
    } catch (err) {
      console.error("Failed to create Google Drive Picker:", err);
      setError("Google Drive Picker requires proper setup. Please enter a URL instead.");
    }
  };

  // Handle picker callback
  const pickerCallback = (data) => {
    if (data.action === window.google.picker.Action.PICKED) {
      const doc = data.docs[0];
      if (doc) {
        const url = doc.url;
        setDriveUrl(url);
        // Auto-submit the selected document after a short delay
        setTimeout(() => {
          const form = document.getElementById('google-drive-form');
          if (form) {
            const event = new Event('submit', { cancelable: true, bubbles: true });
            form.dispatchEvent(event);
          }
        }, 300);
      }
    } else if (data.action === window.google.picker.Action.CANCEL) {
      // User cancelled the picker, no action needed
    }
  };

  const handleAddDrive = async (e) => {
    e.preventDefault();
    
    if (!driveUrl.trim()) {
      setError("Please enter a Google Drive URL or select a file from Google Drive");
      return;
    }
    
    if (!validateDriveUrl(driveUrl)) {
      setError("Please enter a valid Google Drive or Google Docs URL");
      return;
    }
    
    setError(null);
    setSuccess(false);
    setLoading(true);

    try {
      // Create FormData
      const formData = new FormData();
      // Use collection name instead of user ID
      const actualCollectionName = collectionName || localStorage.getItem('collectionName');
      if (actualCollectionName) {
        formData.append("collection_name", actualCollectionName);
      } else {
        formData.append("user_id", userId);
      }
      formData.append("drive_url", driveUrl);

      const response = await api.processDrive(formData);
      const documentObj = {
        id: response.document_id || Date.now().toString(),
        filename: response.title || "Google Drive Document",
        status: response.status === "success" ? "ready" : "processing",
        type: "drive",
        size: null,
        pages: response.pages || null,
        uploadedAt: response.uploaded_at || new Date().toISOString(),
        url: driveUrl,
      };

      setSuccess(true);
      setTimeout(() => {
        setDriveUrl("");
        setLoading(false);
        setSuccess(false);
      }, 1500);

      // Notify parent component
      if (onAddSuccess) {
        onAddSuccess(documentObj);
      }
    } catch (err) {
      console.error("❌ Google Drive processing error:", err);
      // Provide more specific error messages
      if (err.message.includes("403")) {
        setError("Access denied. Please make sure the Google Drive file is publicly shared with 'Anyone with the link' access.");
      } else if (err.message.includes("404")) {
        setError("File not found. Please check the URL and make sure the file is accessible.");
      } else {
        setError(err.message || "Failed to process Google Drive document. Please try again.");
      }
      setLoading(false);
    }
  };

  // Function to retry the Google Drive upload
  const handleRetry = () => {
    const form = document.getElementById('google-drive-form');
    if (form) {
      const event = new Event('submit', { cancelable: true, bubbles: true });
      form.dispatchEvent(event);
    }
  };

  return (
    <div className="w-full">
      <form id="google-drive-form" onSubmit={handleAddDrive} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Add from Google Drive
          </label>
          
          {/* URL Input */}
          <div className="relative mb-3">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <LinkIcon className="h-5 w-5 text-gray-400" />
            </div>
            <input
              type="url"
              value={driveUrl}
              onChange={(e) => setDriveUrl(e.target.value)}
              placeholder="https://drive.google.com/file/... or https://docs.google.com/document/..."
              disabled={loading}
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50"
            />
          </div>
          
          {/* Divider */}
          <div className="relative flex items-center my-3">
            <div className="flex-grow border-t border-gray-300"></div>
            <span className="flex-shrink mx-4 text-gray-500 text-sm">or</span>
            <div className="flex-grow border-t border-gray-300"></div>
          </div>
          
          {/* Google Drive Picker Button */}
          <div className="space-y-3">
            <button
              type="button"
              onClick={showGoogleDrivePicker}
              disabled={loading}
              className={`w-full flex items-center justify-center py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium ${
                loading
                  ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                  : "bg-white text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              }`}
            >
              <FolderOpen className="h-5 w-5 mr-2 text-blue-500" />
              Browse Google Drive
            </button>
            
            {/* Loading indicator */}
            {!isPickerLoaded && !pickerError && (
              <div className="flex items-center justify-center text-gray-500 text-sm">
                <Loader className="animate-spin h-4 w-4 mr-2" />
                Loading Google Drive Picker...
              </div>
            )}
            
            {/* Picker error message */}
            {pickerError && (
              <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                <div className="flex items-start">
                  <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5 mr-2 flex-shrink-0" />
                  <div className="text-sm text-yellow-700">
                    <p className="font-medium">Google Drive Picker unavailable</p>
                    <p className="mt-1">Please enter a Google Drive URL instead.</p>
                  </div>
                </div>
              </div>
            )}
            
            {/* Picker info message */}
            {isPickerLoaded && !pickerError && (
              <div className="p-3 bg-blue-50 border border-blue-100 rounded-md">
                <div className="flex items-start">
                  <Info className="h-4 w-4 text-blue-500 mt-0.5 mr-2 flex-shrink-0" />
                  <div className="text-xs text-blue-700">
                    <p className="font-medium">Google Drive Picker loaded</p>
                    <p className="mt-1">Note: Files must be publicly shared for the picker to work properly.</p>
                  </div>
                </div>
              </div>
            )}
          </div>
          
          <p className="mt-2 text-xs text-gray-500">
            Enter a Google Drive URL or browse and select files directly from your Google Drive
          </p>
        </div>

        <button
          type="submit"
          disabled={loading}
          className={`w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white ${
            loading 
              ? "bg-blue-400 cursor-not-allowed" 
              : "bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          }`}
        >
          {loading ? (
            <>
              <Loader className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" />
              Processing...
            </>
          ) : (
            "Add Google Drive Document"
          )}
        </button>

        {success && (
          <div className="flex items-center justify-center text-green-600 text-sm">
            <CheckCircle className="h-4 w-4 mr-2" />
            Google Drive document added successfully!
          </div>
        )}

        {error && (
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
      </form>
    </div>
  );
};

export default GoogleDriveInput;