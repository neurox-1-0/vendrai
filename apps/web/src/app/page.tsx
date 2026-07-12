"use client";

import React, { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { IconWell } from '@/components/ui/icon-well';
import { Search, Activity, Bell, FileText, X } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';

const data = [
  { name: 'Mon', exceptions: 12 },
  { name: 'Tue', exceptions: 19 },
  { name: 'Wed', exceptions: 15 },
  { name: 'Thu', exceptions: 25 },
  { name: 'Fri', exceptions: 22 },
  { name: 'Sat', exceptions: 5 },
  { name: 'Sun', exceptions: 8 },
];

export default function Dashboard() {
  const [showNotifications, setShowNotifications] = useState(false);
  const [showReportToast, setShowReportToast] = useState(false);

  const handleGenerateReport = () => {
    setShowReportToast(true);
    setTimeout(() => setShowReportToast(false), 3000);
  };

  return (
    <>
      {/* Header */}
      <header className="h-24 flex items-center justify-between px-12 z-50 relative">
        <h2 className="font-display font-bold text-3xl">Active Overview</h2>
        
        <div className="flex items-center gap-8">
          <div className="relative w-80 group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-[var(--color-muted)] group-focus-within:text-[var(--color-accent)] transition-colors" />
            <Input placeholder="Search cases or vendors..." className="pl-12 transition-all group-focus-within:shadow-[var(--shadow-inset-deep)]" />
          </div>
          
          <div className="relative">
            <Button variant="icon" className="relative" onClick={() => setShowNotifications(!showNotifications)}>
              <Bell className="h-5 w-5" />
              <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
            </Button>
            
            <AnimatePresence>
              {showNotifications && (
                <motion.div 
                  initial={{ opacity: 0, y: 10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 10, scale: 0.95 }}
                  className="absolute right-0 mt-4 w-80 bg-[var(--color-clay)] rounded-2xl shadow-[var(--shadow-extruded)] border border-[rgba(255,255,255,0.3)] z-50 overflow-hidden"
                >
                  <div className="p-4 border-b border-[rgba(255,255,255,0.2)] font-bold">Notifications</div>
                  <div className="p-4 space-y-3">
                    <div className="flex gap-3 items-start">
                      <div className="w-2 h-2 mt-1.5 rounded-full bg-red-500 shrink-0" />
                      <div>
                        <p className="text-sm font-bold">High Risk Vendor Detected</p>
                        <p className="text-xs text-[var(--color-muted)]">CASE-8492 flagged for OFAC review.</p>
                      </div>
                    </div>
                    <div className="flex gap-3 items-start">
                      <div className="w-2 h-2 mt-1.5 rounded-full bg-yellow-500 shrink-0" />
                      <div>
                        <p className="text-sm font-bold">Invoice Tolerance Exceeded</p>
                        <p className="text-xs text-[var(--color-muted)]">CASE-8491 value is 15% above PO.</p>
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          
          <div className="h-12 w-12 rounded-full shadow-[var(--shadow-extruded)] border-2 border-[var(--color-clay)] overflow-hidden cursor-pointer hover:scale-105 transition-transform">
            <img src="/user-image.jpg" alt="User Avatar" className="h-full w-full object-cover" onError={(e) => e.currentTarget.src = "https://ui-avatars.com/api/?name=Admin+User&background=6C63FF&color=fff"} />
          </div>
        </div>
      </header>

      {/* Dashboard Grid */}
      <div className="p-12 pt-4 grid grid-cols-1 lg:grid-cols-3 gap-12 z-0 relative">
        
        {/* Main Chart Card */}
        <Card className="lg:col-span-2 min-h-[400px] flex flex-col justify-between">
          <div className="flex justify-between items-start mb-8">
            <div>
              <h3 className="font-bold text-xl mb-2">Exceptions Volume</h3>
              <p className="text-[var(--color-muted)]">Real-time processing metrics</p>
            </div>
            <Button variant="primary" onClick={handleGenerateReport}>Generate Report</Button>
          </div>
          
          <div className="flex-1 rounded-2xl shadow-[var(--shadow-inset-deep)] bg-[var(--color-clay)] relative overflow-hidden p-6">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorExceptions" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-accent)" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="var(--color-accent)" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(0,0,0,0.05)" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: 'var(--color-muted)', fontSize: 12}} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{fill: 'var(--color-muted)', fontSize: 12}} />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--color-clay)', borderRadius: '12px', border: 'none', boxShadow: '5px 5px 10px rgba(163, 177, 198, 0.6), -5px -5px 10px rgba(255, 255, 255, 0.5)' }}
                  itemStyle={{ color: 'var(--color-primary)', fontWeight: 'bold' }}
                />
                <Area type="monotone" dataKey="exceptions" stroke="var(--color-accent)" strokeWidth={3} fillOpacity={1} fill="url(#colorExceptions)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Quick Stats Column */}
        <div className="space-y-12">
          <Card className="p-8">
            <div className="flex items-center gap-6 mb-6">
              <IconWell>
                <Activity className="h-6 w-6" />
              </IconWell>
              <div>
                <h4 className="font-bold text-[var(--color-muted)]">Pending Approval</h4>
                <p className="font-display font-extrabold text-4xl">24</p>
              </div>
            </div>
            <div className="w-full h-3 rounded-full shadow-[var(--shadow-inset-sm)] overflow-hidden">
              <motion.div 
                initial={{ width: 0 }}
                animate={{ width: '60%' }}
                transition={{ duration: 1, ease: 'easeOut' }}
                className="h-full bg-[var(--color-accent)] rounded-full shadow-[var(--shadow-extruded-sm)]" 
              />
            </div>
          </Card>
          
          <Card className="p-8">
            <h3 className="font-bold text-xl mb-6">Agent Status</h3>
            <div className="space-y-6">
              <div className="flex justify-between items-center group">
                <span className="font-medium text-[var(--color-muted)] group-hover:text-[var(--color-primary)] transition-colors">Document Extraction</span>
                <span className="h-3 w-3 bg-green-400 rounded-full shadow-[var(--shadow-extruded-sm)]"></span>
              </div>
              <div className="flex justify-between items-center group">
                <span className="font-medium text-[var(--color-muted)] group-hover:text-[var(--color-primary)] transition-colors">Duplicate Review</span>
                <span className="h-3 w-3 bg-[var(--color-accent)] rounded-full shadow-[var(--shadow-extruded-sm)] animate-pulse"></span>
              </div>
              <div className="flex justify-between items-center group">
                <span className="font-medium text-[var(--color-muted)] group-hover:text-[var(--color-primary)] transition-colors">Risk Analysis</span>
                <span className="h-3 w-3 bg-green-400 rounded-full shadow-[var(--shadow-extruded-sm)]"></span>
              </div>
              <div className="flex justify-between items-center group">
                <span className="font-medium text-[var(--color-muted)] group-hover:text-[var(--color-primary)] transition-colors">Policy Retrieval</span>
                <span className="h-3 w-3 bg-green-400 rounded-full shadow-[var(--shadow-extruded-sm)]"></span>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Toast Notification */}
      <AnimatePresence>
        {showReportToast && (
          <motion.div
            initial={{ opacity: 0, y: 50, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: 50, x: '-50%' }}
            className="fixed bottom-8 left-1/2 flex items-center gap-4 bg-[var(--color-clay)] px-6 py-4 rounded-2xl shadow-[var(--shadow-extruded)] border border-[rgba(255,255,255,0.4)] z-50"
          >
            <div className="w-10 h-10 rounded-full shadow-[var(--shadow-inset-sm)] flex items-center justify-center text-[var(--color-accent)]">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <p className="font-bold">Report Generating</p>
              <p className="text-sm text-[var(--color-muted)]">Your metrics report will download shortly.</p>
            </div>
            <button onClick={() => setShowReportToast(false)} className="ml-4 text-[var(--color-muted)] hover:text-red-500">
              <X className="w-5 h-5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
