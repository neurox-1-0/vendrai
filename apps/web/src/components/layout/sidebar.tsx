"use client";

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { LayoutDashboard, FileText, Users, Activity, Settings, HelpCircle, LogOut } from 'lucide-react';
import { motion } from 'framer-motion';

export function Sidebar() {
  const pathname = usePathname();

  const navItems = [
    { name: 'Dashboard', href: '/', icon: LayoutDashboard },
    { name: 'Case Intake', href: '/cases/new', icon: FileText },
    { name: 'Approvals', href: '/approvals', icon: Users },
    { name: 'Analytics', href: '/analytics', icon: Activity },
  ];

  return (
    <aside className="w-72 flex flex-col justify-between p-8 border-r border-[rgba(255,255,255,0.2)] shadow-[var(--shadow-extruded)] z-10 relative bg-[var(--color-clay)] h-screen shrink-0">
      <div>
        <div className="flex justify-center mb-16">
          <motion.img 
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.5 }}
            src="/Full logo.svg" 
            alt="Vendrai Logo" 
            className="h-24 w-24 object-cover rounded-3xl shadow-[var(--shadow-extruded)]" 
          />
        </div>
        
        <nav className="space-y-4">
          {navItems.map((item) => {
            const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
            return (
              <Link key={item.name} href={item.href} className="block">
                <Button 
                  variant={isActive ? "primary" : "secondary"} 
                  className={`w-full justify-start gap-4 transition-all duration-300 ${isActive ? 'opacity-100' : 'opacity-70 hover:opacity-100'}`}
                >
                  <item.icon className="h-5 w-5" /> {item.name}
                </Button>
              </Link>
            );
          })}
        </nav>
      </div>
      
      <div className="space-y-6 pt-8 border-t border-[rgba(255,255,255,0.2)]">
        <nav className="space-y-4">
          <Button variant="secondary" className="w-full justify-start gap-4 opacity-70 hover:opacity-100">
            <HelpCircle className="h-5 w-5" /> Help & Support
          </Button>
          <Button variant="secondary" className="w-full justify-start gap-4 opacity-70 hover:opacity-100">
            <Settings className="h-5 w-5" /> Settings
          </Button>
        </nav>
        
        <div className="flex items-center justify-between bg-[var(--color-clay)] p-3 rounded-2xl shadow-[var(--shadow-inset-sm)] mt-4 border border-[rgba(255,255,255,0.5)]">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="h-10 w-10 shrink-0 rounded-xl shadow-[var(--shadow-extruded-sm)] overflow-hidden bg-gray-300">
              <img src="/user-image.jpg" alt="User" className="h-full w-full object-cover" onError={(e) => e.currentTarget.src = "https://ui-avatars.com/api/?name=Admin+User&background=6C63FF&color=fff"} />
            </div>
            <div className="truncate">
              <p className="text-sm font-bold text-[var(--color-primary)] truncate">Admin User</p>
              <p className="text-xs text-[var(--color-muted)] truncate">admin@vendrai.ai</p>
            </div>
          </div>
          <button className="p-2 text-[var(--color-muted)] hover:text-red-500 transition-colors">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
