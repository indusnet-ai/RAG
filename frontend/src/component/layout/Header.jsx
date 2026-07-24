import React from 'react';
import { MessageSquare, Menu, Settings, HelpCircle, LogOut } from 'lucide-react';

const Header = ({ onToggleSidebar, onLogout, userName }) => {
  // Get first letter of user's name for avatar, or default to 'U'
  const userInitial = userName ? userName.charAt(0).toUpperCase() : 'U';
  
  return (
    <header className="bg-gradient-to-r from-gray-50 to-gray-100 shadow-[0_4px_8px_#b8b9be] border-b border-gray-300 sticky top-0 z-50">
      <div className="px-4 py-3 flex items-center justify-between">
        {/* Left Section */}
        <div className="flex items-center space-x-3">
          <button
            onClick={onToggleSidebar}
            className="hamburger-button p-2 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] active:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] transition-all duration-200"
          >
            <Menu className="h-5 w-5 text-gray-600" />
          </button>
          
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-lg bg-gradient-to-br to-blue-600 shadow-[3px_3px_6px_#b8b9be,-2px_-2px_4px_#ffffff]">
              <MessageSquare className="h-5 w-5 text-blue-700" />
            </div>
            <h1 className="text-xl font-bold text-gray-900 hidden sm:block">RAG Chatbot</h1>
          </div>
        </div>

        {/* Right Section */}
        <div className="flex items-center space-x-4">
          {/* <button className="p-2 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] active:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] transition-all duration-200">
            <HelpCircle className="h-5 w-5 text-gray-600" />
          </button> */}
          
          {/* <button className="p-2 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] active:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] transition-all duration-200">
            <Settings className="h-5 w-5 text-gray-600" />
          </button> */}
          
          {onLogout && (
            <button 
              onClick={onLogout}
              className="p-2 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] active:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] transition-all duration-200"
              title="Logout"
            >
              <LogOut className="h-5 w-5 text-gray-600" />
            </button>
          )}

          <div className="flex items-center space-x-2 pl-4 border-l border-gray-300">
            {userName && (
              <span className="text-sm text-gray-700 font-medium hidden sm:block">
                Hi, {userName}
              </span>
            )}
            <div className="h-9 w-9 bg-gradient-to-br to-blue-600 rounded-full flex items-center justify-center shadow-[3px_3px_6px_#b8b9be,-2px_-2px_4px_#ffffff]">
              <span className="text-sm font-semibold text-blue-700">{userInitial}</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;