"use client";

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { LayoutDashboard, FileText, Users, Activity, Settings } from 'lucide-react';
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
    <aside className="w-64 flex flex-col justify-between p-8 border-r border-[rgba(255,255,255,0.2)] shadow-[var(--shadow-extruded)] z-10 relative bg-[var(--color-clay)] h-screen shrink-0">
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
      
      <Button variant="icon" className="mx-auto w-12 h-12">
        <Settings className="h-5 w-5" />
      </Button>
    </aside>
  );
}
