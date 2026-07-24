import React, { useState } from "react";
import { FileText as FileTextIcon, AlertCircle, CheckCircle, Loader, RefreshCw } from "lucide-react";
import api from "../../services/api";

const TextInput = ({ userId = "55", onAddSuccess, collectionName }) => {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  const handleAddText = async (e) => {
    e.preventDefault();
    
    if (!title.trim()) {
      setError("Please enter a title");
      return;
    }
    
    if (!content.trim()) {
      setError("Please enter some content");
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
      formData.append("title", title);
      formData.append("content", content);

      const response = await api.processText(formData);

      // Create document object from response
      // Match the format of server-side documents to prevent UI flickering
      const documentObj = {
        id: response.document_id || Date.now().toString(),
        filename: title,
        status: response.status === "success" ? "ready" : "processing",
        type: "text",
        size: null,
        pages: response.pages || null,
        uploadedAt: response.uploaded_at || new Date().toISOString(),
        content: content,
      };

      setSuccess(true);
      
      // Reset after showing success, but don't close the panel if we're in an active chat
      // The parent component will handle closing the panel when appropriate
      setTimeout(() => {
        setTitle("");
        setContent("");
        setLoading(false);
        setSuccess(false);
      }, 1500);

      // Notify parent component
      if (onAddSuccess) {
        onAddSuccess(documentObj);
      }
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  // Function to retry the text processing
  const handleRetry = () => {
    const form = document.getElementById('text-input-form');
    if (form) {
      const event = new Event('submit', { cancelable: true, bubbles: true });
      form.dispatchEvent(event);
    }
  };

  return (
    <div className="w-full">
      <form id="text-input-form" onSubmit={handleAddText} className="space-y-4">
        <div>
          <label htmlFor="text-title" className="block text-sm font-medium text-gray-700 mb-1">
            Title
          </label>
          <input
            type="text"
            id="text-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Enter a title for your text"
            disabled={loading}
            className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50"
          />
        </div>
        
        <div>
          <label htmlFor="text-content" className="block text-sm font-medium text-gray-700 mb-1">
            Content
          </label>
          <textarea
            id="text-content"
            rows={6}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Enter your text content here..."
            disabled={loading}
            className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50"
          />
          <p className="mt-1 text-xs text-gray-500">
            Enter any text content you want to add to your knowledge base
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
            "Add Text Content"
          )}
        </button>

        {success && (
          <div className="flex items-center justify-center text-green-600 text-sm">
            <CheckCircle className="h-4 w-4 mr-2" />
            Text content added successfully!
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

export default TextInput;