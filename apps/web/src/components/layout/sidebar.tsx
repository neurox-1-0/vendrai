"use client";

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { LayoutDashboard, FileText, Users, Activity, Settings, HelpCircle, ClipboardList } from 'lucide-react';
import { motion } from 'framer-motion';
import Image from 'next/image';

export function Sidebar() {
  const pathname = usePathname();

  const navItems = [
    { name: 'Dashboard', href: '/', icon: LayoutDashboard },
    { name: 'Case Intake', href: '/cases/new', icon: FileText },
    { name: 'Approvals', href: '/approvals', icon: Users },
    { name: 'Analytics', href: '/analytics', icon: Activity },
    { name: 'Reports', href: '/reports', icon: ClipboardList },
  ];

  return (
    <>
    <aside className="hidden w-72 flex-col justify-between border-r border-white/20 bg-[var(--color-clay)] p-8 shadow-[var(--shadow-extruded)] md:flex md:h-screen md:shrink-0" aria-label="Primary navigation">
      <div>
        <div className="flex justify-center mb-16">
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.5 }}
            className="rounded-3xl shadow-[var(--shadow-extruded)]"
          >
            <Image src="/Full logo.svg" alt="NeuroX" width={96} height={96} className="h-24 w-24 rounded-3xl object-cover" priority />
          </motion.div>
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
          <Button type="button" variant="secondary" className="w-full justify-start gap-4 opacity-70 hover:opacity-100">
            <HelpCircle className="h-5 w-5" /> Help & Support
          </Button>
          <Button type="button" variant="secondary" className="w-full justify-start gap-4 opacity-70 hover:opacity-100">
            <Settings className="h-5 w-5" /> Settings
          </Button>
        </nav>
      </div>
    </aside>
    <nav className="fixed inset-x-0 bottom-0 z-40 flex justify-around border-t border-white/40 bg-[var(--color-clay)] p-2 shadow-[var(--shadow-extruded)] md:hidden" aria-label="Mobile navigation">
      {navItems.map((item) => {
        const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
        return (
          <Link key={item.name} href={item.href} aria-current={isActive ? "page" : undefined} className={`flex min-w-14 flex-col items-center gap-1 rounded-xl px-2 py-2 text-[10px] font-bold ${isActive ? "bg-[var(--color-accent)] text-white" : "text-[var(--color-muted)]"}`}>
            <item.icon className="h-5 w-5" aria-hidden="true" />{item.name}
          </Link>
        );
      })}
    </nav>
    </>
  );
}
