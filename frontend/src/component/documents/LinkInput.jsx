import React, { useState } from "react";
import { Link as LinkIcon, AlertCircle, CheckCircle, Loader, RefreshCw, Info } from "lucide-react";
import api from "../../services/api";

const LinkInput = ({ userId = "55", onAddSuccess, collectionName }) => {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  const validateUrl = (string) => {
    try {
      new URL(string);
      return true;
    } catch (_) {
      return false;
    }
  };

  const isYouTubeUrl = (url) => {
    const youtubeRegex = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$/;
    return youtubeRegex.test(url);
  };

  const handleAddLink = async (e) => {
    e.preventDefault();
    if (!url.trim()) {
      setError("Please enter a URL");
      return;
    }
    
    if (!validateUrl(url)) {
      setError("Please enter a valid URL");
      return;
    }
    
    setError(null);
    setSuccess(false);
    setLoading(true);

    try {
      // Use collection name instead of user ID
      const actualCollectionName = collectionName || localStorage.getItem('collectionName');
      if (!actualCollectionName) {
        throw new Error("No collection name available for document upload");
      }
      
      if (isYouTubeUrl(url)) {
        // Handle YouTube URL
        const data = {
          urls: url,
          collection_name: actualCollectionName
        };
        
        const response = await api.processYouTubeUrl(data);

        // Check if YouTube processing failed
        if (response.status === "failed") {
          let errorMessage = "Failed to process YouTube video.";
          if (response.error) {
            // Handle common YouTube errors
            if (response.error.includes("403")) {
              errorMessage = "Unable to access this YouTube video. The video may be private, age-restricted, or unavailable in your region.";
            } else if (response.error.includes("404")) {
              errorMessage = "YouTube video not found. Please check the URL.";
            } else {
           
              errorMessage="something went wrong"
            }
          }
          throw new Error(errorMessage);
        }

        // Create document object from response with better metadata for suggestions
        // Match the format of server-side documents to prevent UI flickering
        const documentObj = {
          id: response.document_id || Date.now().toString(),
          filename: response.video_title || "YouTube Video",
          status: response.status === "success" ? "ready" : "processing",
          type: "link",
          size: null,
          pages: response.chunks_inserted || null,
          uploadedAt: response.uploaded_at || new Date().toISOString(),
          sourceType: "youtube",
          url: response.url || url
        };

        setSuccess(true);
        
   
        setTimeout(() => {
          setUrl("");
          setLoading(false);
          setSuccess(false);
        }, 1500);

        // Notify parent component
        if (onAddSuccess) {
          onAddSuccess(documentObj);
        }
      } else {
        // Handle regular web page URL
        const data = {
          urls: url,
          collection_name: actualCollectionName,
          crawl: true,
          recursive_crawl: true,
          max_pages_per_url: 10
        };
        
        const response = await api.processWebUrl(data);

        // Create document object from response with better metadata for suggestions
        // Match the format of server-side documents to prevent UI flickering
        const documentObj = {
          id: response.document_id || Date.now().toString(),
          filename: response.title || new URL(url).hostname,
          status: response.status === "success" ? "ready" : "processing",
          type: "link",
          size: null,
          pages: response.pages_crawled || null,
          uploadedAt: response.uploaded_at || new Date().toISOString(),
          sourceType: "webpage",
          url: url
        };

        setSuccess(true);

        setTimeout(() => {
          setUrl("");
          setLoading(false);
          setSuccess(false);
        }, 1500);

        // Notify parent component
        if (onAddSuccess) {
          onAddSuccess(documentObj);
        }
      }
    } catch (err) {
      setError(err.message || "An error occurred while processing the URL");
      setLoading(false);
    }
  };

  // Function to retry the link processing
  const handleRetry = () => {
    const form = document.getElementById('link-input-form');
    if (form) {
      const event = new Event('submit', { cancelable: true, bubbles: true });
      form.dispatchEvent(event);
    }
  };

  return (
    <div className="w-full">
      <form id="link-input-form" onSubmit={handleAddLink} className="space-y-4">
        <div>
          <label htmlFor="url-input" className="block text-sm font-medium text-gray-700 mb-1">
            Web Page or YouTube URL
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <LinkIcon className="h-5 w-5 text-gray-400" />
            </div>
            <input
              type="url"
              id="url-input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/article or https://youtube.com/watch?v=..."
              disabled={loading}
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50"
            />
          </div>
          <p className="mt-1 text-xs text-gray-500">
            Enter a web page URL or YouTube video URL to add to your knowledge base
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
            "Add URL"
          )}
        </button>

        {success && (
          <div className="flex items-center justify-center text-green-600 text-sm">
            <CheckCircle className="h-4 w-4 mr-2" />
            URL added successfully!
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
                Retry Processing
              </button>
            )}
          </div>
        )}
      </form>
    </div>
  );
};

export default LinkInput;