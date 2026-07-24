import React, { useState, useEffect, useRef } from 'react';
import Header from './Header';
import Sidebar from './Sidebar';
import { X } from 'lucide-react';

const Layout = ({ 
  children, 
  documents, 
  selectedDocumentIds,
  onToggleSelectDocument,
  onDocumentUpload, 
  onDocumentDelete, 
  chats, 
  currentChatId, 
  onNewChat, 
  onLogout, 
  collectionName,
  collections,
  onCollectionSelect,
  fetchCollections,
  onCollectionDelete
}) => {
  const [triggerUpload, setTriggerUpload] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true); 
  const [userName, setUserName] = useState('');
  const documentUploadRef = useRef(null);

  useEffect(() => {

    const name = localStorage.getItem('userName');
    if (name) {
      setUserName(name);
    }

    const handleResize = () => {
      if (window.innerWidth < 768) {
        setSidebarOpen(false); 
      } else {
        setSidebarOpen(true); 
      }
    };
    
    // Set initial state
    handleResize();
    
    // Add resize listener
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Close sidebar when clicking outside on mobile
  useEffect(() => {
    const handleClickOutside = (event) => {
      const sidebar = document.querySelector('.sidebar-container');
      const hamburger = document.querySelector('.hamburger-button');
      
      if (sidebar && !sidebar.contains(event.target) && 
          hamburger && !hamburger.contains(event.target) && 
          sidebarOpen && window.innerWidth < 768) {
        setSidebarOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [sidebarOpen]);
  // ADD THIS FUNCTION
  const handlePaperclipClick = () => {
  setSidebarOpen(true);
  setTriggerUpload(true);
  
  setTimeout(() => {
    documentUploadRef.current?.triggerFileSelect();
    setTriggerUpload(false);
  }, 300);
};

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex flex-col">
      <Header onToggleSidebar={() => setSidebarOpen(!sidebarOpen)} onLogout={onLogout} userName={userName} />
      
      <div className="flex flex-1 relative overflow-hidden">
        {/* Sidebar - Smooth animation with mobile overlay */}
        <div 
          className={`sidebar-container flex-shrink-0 transition-all duration-300 ease-in-out overflow-hidden
            ${sidebarOpen ? 'w-80 md:w-64 lg:w-80' : 'w-0'}
            fixed md:relative z-30 h-[calc(100vh-57px)] md:h-auto
          `}
        >
          <div className="w-80 md:w-64 lg:w-80 h-full">
            {/* Close button for mobile */}
            <div className="md:hidden absolute top-0 right-0 m-4 z-50">
              <button 
                onClick={() => setSidebarOpen(false)}
                className="p-2 rounded-full bg-gradient-to-br from-gray-50 to-gray-100 shadow-[4px_4px_8px_#b8b9be,-4px_-4px_8px_#ffffff] text-gray-600 hover:text-gray-900 hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] active:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] transition-all duration-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            
            <Sidebar 
              triggerUpload={triggerUpload}
              documents={documents}
              selectedDocumentIds={selectedDocumentIds}
              onToggleSelect={onToggleSelectDocument}
              onDocumentUpload={onDocumentUpload}
              onDocumentDelete={onDocumentDelete}
              chats={chats}
              currentChatId={currentChatId}
              onNewChat={onNewChat}
              collectionName={collectionName}
              documentUploadRef={documentUploadRef}
              collections={collections}
              onCollectionSelect={onCollectionSelect}
              fetchCollections={fetchCollections}
              onCollectionDelete={onCollectionDelete}
            />
          </div>
        </div>

        {/* Overlay for mobile when sidebar is open - with blur effect */}
        {sidebarOpen && (
          <div 
            className="fixed inset-0 bg-black bg-opacity-30 backdrop-blur-sm z-20 md:hidden transition-opacity duration-300"
            onClick={() => setSidebarOpen(false)}
          ></div>
        )}

        {/* Main Content - Adjusts width based on sidebar state */}
        <div className="flex-1 w-full transition-all duration-300 md:ml-0">
        {React.cloneElement(children, { onTriggerFileUpload: handlePaperclipClick })}
        </div>
      </div>
    </div>
  );
};

export default Layout;