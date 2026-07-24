import React, { useState } from 'react';
import { FileText, Link as LinkIcon, FileText as FileTextIcon, HardDrive, Mic, Trash2, AlertTriangle, Play, Download, Youtube } from 'lucide-react';

const DocumentCard = ({ document, isSelected, onToggleSelect, onDelete }) => {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const getStatusColor = (status) => {
    switch (status) {
      case 'ready':
        return 'text-green-600 bg-green-50';
      case 'processing':
        return 'text-yellow-600 bg-yellow-50';
      case 'failed':
        return 'text-red-600 bg-red-50';
      default:
        return 'text-gray-600 bg-gray-50';
    }
  };

  console.log(document);

  const getDocumentIcon = (type, sourceType) => {
    if (type === 'link') {
      if (sourceType === 'youtube') {
        return <Youtube className="h-5 w-5 text-red-600" />;
      } else {
        return <LinkIcon className="h-5 w-5 text-blue-600" />;
      }
    }
    switch (type) {
      case 'text':
        return <FileTextIcon className="h-5 w-5 text-green-600" />;
      case 'drive':
        return <HardDrive className="h-5 w-5 text-purple-600" />;
      case 'podcast':
        return <Mic className="h-5 w-5 text-red-600" />;
      default: // file
        return <FileText className="h-5 w-5 text-blue-600" />;
    }
  };

  const getDocumentTypeLabel = (type, sourceType) => {
    if (type === 'link') {
      if (sourceType === 'youtube') {
        return 'YouTube';
      } else {
        return 'Web Page';
      }
    }
    switch (type) {
      case 'text':
        return 'Text';
      case 'drive':
        return 'Google Drive';
      case 'podcast':
        return 'Podcast';
      default: // file
        return 'File';
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const handleDelete = () => {
    onDelete(document.id);
    setShowDeleteConfirm(false);
  };

  // Function to handle document viewing/downloading
  const handleDocumentView = () => {
    // For links (including YouTube), open in a new tab
    if (document.type === 'link' && document.url) {
      window.open(document.url, '_blank');
      return;
    }

    // For podcasts with audio URLs, open in a new tab
    if (document.type === 'podcast' && document.audioUrl) {
      window.open(document.audioUrl, '_blank');
      return;
    }

    // For file uploads, attempt to construct a download URL
    // if (document.id && document.type === 'file') {
    //   const API_BASE_URL = 'http://127.0.0.1:8002';
    //   const downloadUrl = `${API_BASE_URL}/api/documents/${document.id}/download`;
      
    //   // Create a temporary link and trigger download
    //   const link = document.createElement('a');
    //   link.href = downloadUrl;
    //   link.download = document.filename || 'document';
    //   link.target = '_blank';
    //   document.body.appendChild(link);
    //   link.click();
    //   document.body.removeChild(link);
    //   return;
    // }

    // For Google Drive documents, open the URL in a new tab
    if (document.type === 'drive' && document.url) {
      window.open(document.url, '_blank');
      return;
    }

    // For text documents, we could show content in a modal, but for now we'll show an alert
    if (document.type === 'text') {
      alert('Text document viewing is not yet implemented. This feature will be added soon.');
      return;
    }

    // Fallback for unknown document types
    // alert('Document viewing/downloading is not available for this document type.');
  };

  return (
    <>
      <div 
        className={`group border rounded-lg p-3 hover:shadow-md transition-all cursor-pointer ${
          isSelected 
            ? 'bg-blue-50/20 border-blue-400' 
            : 'bg-white border-gray-200 hover:border-blue-300'
        }`}
        onClick={handleDocumentView}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-start space-x-3 flex-1 min-w-0">
            <div className="flex-shrink-0 mt-1" onClick={(e) => e.stopPropagation()}>
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggleSelect && onToggleSelect(document.id)}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer transition-all duration-150"
              />
            </div>

            <div className="flex-shrink-0 mt-0.5">
              {getDocumentIcon(document.type, document.sourceType)}
            </div>
            
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">
                {document.filename}
              </p>
              
              <div className="flex items-center space-x-2 mt-1">
                <span className={`text-xs px-2 py-0.5 rounded-full ${getStatusColor(document.status)}`}>
                  {document.status}
                </span>
                
                <span className="text-xs text-gray-500">
                  {getDocumentTypeLabel(document.type, document.sourceType)}
                </span>
                
                {document.pages && (
                  <span className="text-xs text-gray-500">
                    {document.pages} pages
                  </span>
                )}
                
                {document.size && (
                  <span className="text-xs text-gray-500">
                    {document.chunks_inserted}
                  </span>
                )}
              </div>
              
              {document.url && (
                <p className="text-xs text-gray-500 truncate mt-1">
                  {document.url}
                </p>
              )}
              
              {document.type === 'podcast' && document.audioUrl && (
                <div className="mt-2 flex items-center space-x-2">
                  <audio controls className="w-full h-8">
                    <source src={document.audioUrl} type="audio/wav" />
                    Your browser does not support the audio element.
                  </audio>
                </div>
              )}
            </div>
          </div>

          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowDeleteConfirm(true);
            }}
            className="p-1.5 hover:bg-red-50 rounded transition-all"
            title="Delete document"
          >
            <Trash2 className="h-4 w-4 text-red-600" />
          </button>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-md w-full p-6">
            <div className="flex items-center mb-4">
              <AlertTriangle className="h-6 w-6 text-yellow-500 mr-2" />
              <h3 className="text-lg font-medium text-gray-900">Confirm Deletion</h3>
            </div>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete "{document.filename}"? This action cannot be undone.
            </p>
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default DocumentCard;