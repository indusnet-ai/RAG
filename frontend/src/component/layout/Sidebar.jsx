import React, { useState, useEffect } from 'react';
import DocumentUpload from '../documents/DocumentUpload';
import DocumentList from '../documents/DocumentList';
import LinkInput from '../documents/LinkInput';
import PodcastInput from '../documents/PodcastInput';
import { FileText, Plus, X, Link, FileText as FileTextIcon, Mic, PenSquare, MessageCircle, Clock, MoreVertical, Trash2 } from 'lucide-react';

const Sidebar = ({ 
  documents = [], 
  selectedDocumentIds = [],
  onToggleSelect,
  onDocumentUpload, 
  onDocumentDelete, 
  onNewChat, 
  collectionName, 
  documentUploadRef, 
  triggerUpload,
  collections = [],
  onCollectionSelect,
  fetchCollections,
  onCollectionDelete
}) => {
  const [activePanel, setActivePanel] = useState(null); // 'sources' or 'chat'
  const [activeTab, setActiveTab] = useState('file');
  const [dropdownOpen, setDropdownOpen] = useState(null); // Track which collection's dropdown is open
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [collectionToDelete, setCollectionToDelete] = useState(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownOpen && !event.target.closest('.dropdown-menu')) {
        setDropdownOpen(null);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownOpen]);

  useEffect(() => {
    if (triggerUpload) {
      setActivePanel('sources');
      setActiveTab('file');
    }
  }, [triggerUpload]);

  const handleUploadSuccess = (newDoc) => {
    if (onDocumentUpload) {
      onDocumentUpload(newDoc);
    }
  };

  const handleDelete = (id) => {
    if (onDocumentDelete) {
      onDocumentDelete(id);
    }
  };

  const renderUploadContent = () => {
    switch (activeTab) {
      case 'link':
        return <LinkInput onAddSuccess={handleUploadSuccess} collectionName={collectionName} />;
      case 'podcast':
        return <PodcastInput onAddSuccess={handleUploadSuccess} collectionName={collectionName} />;
      default:
        return <DocumentUpload ref={documentUploadRef} onUploadSuccess={handleUploadSuccess} collectionName={collectionName} />;
    }
  };

  // Format date for display
  function formatDate(dateString) {
  const date = new Date(dateString);

  // Convert UTC → IST manually
  const IST_OFFSET = 5.5 * 60 * 60 * 1000;
  const istDate = new Date(date.getTime() + IST_OFFSET);

  return istDate.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}


  return (
    <aside className="w-80 h-[calc(98vh-57px)] bg-gradient-to-br from-gray-50 to-gray-100 text-gray-800 flex flex-col md:w-64 lg:w-80 relative border-r border-gray-300" style={{ boxShadow: '4px 0 8px #b8b9be' }}>
      {/* New Chat Button - Neumorphic Style */}
      <div className="flex-shrink-0 p-3 border-b border-gray-200 relative" style={{ boxShadow: '0 1px 0 rgba(255,255,255,0.5), 0 2px 4px rgba(184,185,190,0.2)' }}>
        <button
          onClick={onNewChat}
          className="w-full px-4 py-3 bg-gradient-to-br from-gray-50 to-gray-100 text-gray-700 rounded-xl shadow-[4px_4px_8px_#b8b9be,-4px_-4px_8px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] active:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] transition-all duration-200 flex items-center justify-center gap-2 text-sm font-medium"
        >
          <PenSquare className="h-4 w-4" />
          <span>New chat</span>
        </button>
      </div>

      {/* Chat History Toggle - Neumorphic Style */}
      <div className="flex-shrink-0 p-3 border-b border-gray-200 relative" style={{ boxShadow: '0 1px 0 rgba(255,255,255,0.5), 0 2px 4px rgba(184,185,190,0.2)' }}>
        <button
          onClick={() => {
            // Toggle chat panel and close sources panel
            setActivePanel(activePanel === 'chat' ? null : 'chat');
            // Fetch collections when opening chat history
            if (activePanel !== 'chat') {
              fetchCollections();
            }
          }}
          className={`w-full px-4 py-3 text-sm rounded-xl transition-all duration-200 flex items-center justify-between ${
            activePanel === 'chat'
              ? 'bg-gradient-to-br from-gray-50 to-gray-100 shadow-[inset_3px_3px_6px_#b8b9be,inset_-3px_-3px_6px_#ffffff] text-gray-800'
              : 'bg-gradient-to-br from-gray-50 to-gray-100 shadow-[4px_4px_8px_#b8b9be,-4px_-4px_8px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] text-gray-700'
          }`}
        >
          <span className="flex items-center gap-2 font-medium">
            <Clock className="h-4 w-4" />
            <span>Chat History</span>
          </span>
          {activePanel === 'chat' ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
        </button>
      </div>

      {/* Chat History Panel */}
      {activePanel === 'chat' && (
        <div className="flex-shrink-0 border-b border-gray-200 relative" style={{ boxShadow: '0 1px 0 rgba(255,255,255,0.5), 0 2px 4px rgba(184,185,190,0.2)' }}>
          <div className="p-3 max-h-60 overflow-y-auto">
            {collections.length === 0 ? (
              <div className="text-center py-4 text-gray-500 text-sm">
                No chat history found
              </div>
            ) : (
              <div className="space-y-2">
                {collections.map((collection) => (
                  <div 
                    key={collection.name}
                    className={`p-3 rounded-lg cursor-pointer transition-all duration-200 relative ${
                      collectionName === collection.name
                        ? 'bg-gradient-to-br from-blue-50 to-blue-100 border border-blue-200'
                        : 'bg-gradient-to-br from-gray-50 to-gray-100 hover:bg-gradient-to-br hover:from-gray-100 hover:to-gray-200'
                    }`}
                  >
                    <div 
                      className="flex items-start gap-2"
                      onClick={() => onCollectionSelect(collection.name)}
                    >
                      <MessageCircle className="h-4 w-4 text-gray-600 mt-0.5 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm text-gray-800 truncate">
                          {collection.chat_title}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          Created: {formatDate(collection.created_at)}
                        </div>
                        {collection.last_message && (
                          <div className="text-xs text-gray-600 mt-1 truncate">
                            Last: {collection.last_message.substring(0, 30)}...
                          </div>
                        )}
                      </div>
                    </div>
                    
                    {/* Three-dot menu for delete option */}
                    <div className="absolute top-2 right-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDropdownOpen(dropdownOpen === collection.name ? null : collection.name);
                        }}
                        className="p-1 rounded-full hover:bg-gray-200 text-gray-500 hover:text-gray-700"
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>
                      
                      {/* Dropdown menu */}
                      {dropdownOpen === collection.name && (
                        <div className="dropdown-menu absolute right-0 mt-1 w-40 bg-white rounded-md shadow-lg py-1 z-50 border border-gray-200">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setCollectionToDelete(collection.name);
                              setShowDeleteConfirm(true);
                              setDropdownOpen(null);
                            }}
                            className="flex items-center w-full px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Delete Chat
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add Sources Toggle - Neumorphic Style */}
      <div className="flex-shrink-0 p-3 border-b border-gray-200 relative" style={{ boxShadow: '0 1px 0 rgba(255,255,255,0.5), 0 2px 4px rgba(184,185,190,0.2)' }}>
        <button
          onClick={() => {
            // Toggle sources panel and close chat panel
            setActivePanel(activePanel === 'sources' ? null : 'sources');
            if (activePanel !== 'sources') {
              setActiveTab('file');
            }
          }}
          className={`w-full px-4 py-3 text-sm rounded-xl transition-all duration-200 flex items-center justify-between ${
            activePanel === 'sources'
              ? 'bg-gradient-to-br from-gray-50 to-gray-100 shadow-[inset_3px_3px_6px_#b8b9be,inset_-3px_-3px_6px_#ffffff] text-gray-800'
              : 'bg-gradient-to-br from-gray-50 to-gray-100 shadow-[4px_4px_8px_#b8b9be,-4px_-4px_8px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] text-gray-700'
          }`}
        >
          <span className="flex items-center gap-2 font-medium">
            <FileText className="h-4 w-4" />
            <span>Sources</span>
          </span>
          {activePanel === 'sources' ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
        </button>
      </div>

      {/* Scrollable Content Area */}
      <div className="flex-1 overflow-y-auto">
        {/* Upload Panel */}
        {activePanel === 'sources' && (
          <div className="flex-shrink-0 border-b border-gray-200 relative" style={{ boxShadow: '0 1px 0 rgba(255,255,255,0.5), 0 2px 4px rgba(184,185,190,0.2)' }}>
            <div className="p-3">
              {/* Upload Type Tabs - Neumorphic Style */}
              <div className="flex gap-2 mb-4 bg-gradient-to-br from-gray-50 to-gray-100 p-1.5 rounded-xl shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff]">
                <button
                  onClick={() => setActiveTab('file')}
                  className={`flex-1 px-3 py-2 text-xs rounded-lg transition-all duration-200 font-medium ${
                    activeTab === 'file'
                      ? 'bg-gradient-to-br from-gray-50 to-gray-100 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] text-gray-800'
                      : 'text-gray-600 hover:text-gray-800'
                  }`}
                >
                  <FileTextIcon className="h-3.5 w-3.5 inline mr-1" />
                  <span className="hidden sm:inline">File</span>
                </button>
                
                <button
                  onClick={() => setActiveTab('link')}
                  className={`flex-1 px-3 py-2 text-xs rounded-lg transition-all duration-200 font-medium ${
                    activeTab === 'link'
                      ? 'bg-gradient-to-br from-gray-50 to-gray-100 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] text-gray-800'
                      : 'text-gray-600 hover:text-gray-800'
                  }`}
                >
                  <Link className="h-3.5 w-3.5 inline mr-1" />
                  <span className="hidden sm:inline">Link</span>
                </button>
                
                <button
                  onClick={() => setActiveTab('podcast')}
                  className={`flex-1 px-3 py-2 text-xs rounded-lg transition-all duration-200 font-medium ${
                    activeTab === 'podcast'
                      ? 'bg-gradient-to-br from-gray-50 to-gray-100 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] text-gray-800'
                      : 'text-gray-600 hover:text-gray-800'
                  }`}
                >
                  <Mic className="h-3.5 w-3.5 inline mr-1" />
                  <span className="hidden sm:inline">Podcast</span>
                </button>
              </div>

              {/* Upload Content - Neumorphic Container */}
              <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl p-3 shadow-[inset_3px_3px_6px_#b8b9be,inset_-3px_-3px_6px_#ffffff]">
                {renderUploadContent()}
              </div>
            </div>
          </div>
        )}

        {/* Document List */}
        {documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center text-center px-4 py-8">
            <div className="w-16 h-16 bg-gradient-to-br from-gray-50 to-gray-100 rounded-full flex items-center justify-center mb-4 shadow-[4px_4px_8px_#b8b9be,-4px_-4px_8px_#ffffff]">
              <FileText className="h-7 w-7 text-gray-400" />
            </div>
            <p className="text-sm text-gray-600 font-medium">No documents yet</p>
            <p className="text-xs text-gray-500 mt-1">Add sources to get started</p>
          </div>
        ) : (
          <div className="p-3">
            <DocumentList
              documents={documents}
              selectedDocumentIds={selectedDocumentIds}
              onToggleSelect={onToggleSelect}
              onDelete={handleDelete}
              loading={false}
            />
          </div>
        )}
      </div>

      {/* Footer Info - Neumorphic Style */}
      <div className="flex-shrink-0 p-3 border-t border-gray-200 relative" style={{ boxShadow: '0 -1px 0 rgba(255,255,255,0.5), 0 -2px 4px rgba(184,185,190,0.2)' }}>
        <div className="text-xs text-gray-600 text-center font-medium bg-gradient-to-br from-gray-50 to-gray-100 py-2 px-4 rounded-lg shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff]">
          {documents.length} {documents.length === 1 ? 'document' : 'documents'}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 max-w-[90%] shadow-xl">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Delete Chat History</h3>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete this chat history? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 text-gray-600 hover:text-gray-800 font-medium rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (onCollectionDelete && collectionToDelete) {
                    onCollectionDelete(collectionToDelete);
                  }
                  setShowDeleteConfirm(false);
                  setCollectionToDelete(null);
                }}
                className="px-4 py-2 bg-red-600 text-white font-medium rounded-lg hover:bg-red-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};

export default Sidebar;