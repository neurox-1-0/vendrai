"use client";

import React, { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { IconWell } from '@/components/ui/icon-well';
import { Search, Activity, Bell, FileText, X, LogOut, User } from 'lucide-react';
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
  const [showProfileMenu, setShowProfileMenu] = useState(false);
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
          
          <div className="relative">
            <div 
              onClick={() => setShowProfileMenu(!showProfileMenu)}
              className="h-12 w-12 rounded-full shadow-[var(--shadow-extruded)] border-2 border-[var(--color-clay)] overflow-hidden cursor-pointer hover:scale-105 transition-transform"
            >
              <img src="/user-image.jpg" alt="User Avatar" className="h-full w-full object-cover" onError={(e) => e.currentTarget.src = "https://ui-avatars.com/api/?name=Admin+User&background=6C63FF&color=fff"} />
            </div>
            
            <AnimatePresence>
              {showProfileMenu && (
                <motion.div 
                  initial={{ opacity: 0, y: 10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 10, scale: 0.95 }}
                  className="absolute right-0 mt-4 w-64 bg-[var(--color-clay)] rounded-2xl shadow-[var(--shadow-extruded)] border border-[rgba(255,255,255,0.3)] z-50 overflow-hidden"
                >
                  <div className="p-4 border-b border-[rgba(255,255,255,0.2)] flex items-center gap-3">
                    <div className="h-10 w-10 shrink-0 rounded-xl shadow-[var(--shadow-extruded-sm)] overflow-hidden bg-gray-300">
                      <img src="/user-image.jpg" alt="User" className="h-full w-full object-cover" onError={(e) => e.currentTarget.src = "https://ui-avatars.com/api/?name=Admin+User&background=6C63FF&color=fff"} />
                    </div>
                    <div className="truncate">
                      <p className="text-sm font-bold text-[var(--color-primary)] truncate">Admin User</p>
                      <p className="text-xs text-[var(--color-muted)] truncate">admin@vendrai.ai</p>
                    </div>
                  </div>
                  <div className="p-2">
                    <button className="w-full flex items-center gap-3 px-4 py-2 text-sm text-[var(--color-primary)] rounded-xl hover:bg-[rgba(108,99,255,0.1)] transition-colors">
                      <User className="h-4 w-4" /> Profile Settings
                    </button>
                    <button className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-500 rounded-xl hover:bg-[rgba(239,68,68,0.1)] transition-colors mt-1">
                      <LogOut className="h-4 w-4" /> Log out
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </header>

      {/* Dashboard Grid */}
      <div className="p-12 pt-4 grid grid-cols-1 lg:grid-cols-3 gap-12 z-0 relative">
        
        {/* Main Chart Card */}
        <Card className="lg:col-span-2 min-h-[400px] flex flex-col justify-between">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h3 className="font-bold text-xl mb-1">Exceptions Volume</h3>
              <p className="text-[var(--color-muted)] text-sm mb-4">Real-time processing metrics</p>
              
              <div className="inline-flex items-center gap-2 bg-[rgba(108,99,255,0.1)] border border-[rgba(108,99,255,0.2)] rounded-lg px-3 py-1.5">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-accent)] opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--color-accent)]"></span>
                </span>
                <span className="text-xs font-medium text-[var(--color-accent)]">AI Insight: Volume is up 15% today due to mid-month invoicing.</span>
              </div>
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

      {/* Bottom Row - Activity & Logs */}
      <div className="px-12 pb-12 grid grid-cols-1 lg:grid-cols-2 gap-12 z-0 relative">
        {/* Recent Activity Feed */}
        <Card className="p-8">
          <h3 className="font-bold text-xl mb-6 flex items-center gap-2">
            <Activity className="w-5 h-5 text-[var(--color-accent)]" /> Recent Activity
          </h3>
          <div className="space-y-6 relative before:absolute before:inset-0 before:ml-2.5 before:-translate-x-px before:h-full before:w-0.5 before:bg-[var(--color-clay)] before:shadow-[var(--shadow-extruded-sm)]">
            {[
              { id: 'CASE-8493', action: 'Invoice Extracted', time: 'Just now', color: 'bg-blue-500' },
              { id: 'CASE-8492', action: 'Flagged for OFAC Review', time: '2 mins ago', color: 'bg-red-500' },
              { id: 'CASE-8491', action: 'Tolerance Exceeded (15%)', time: '1 hour ago', color: 'bg-yellow-500' },
              { id: 'CASE-8490', action: 'Approved by CFO', time: '3 hours ago', color: 'bg-green-500' },
            ].map((item, i) => (
              <div key={i} className="relative flex items-start gap-6 group">
                <div className={`w-5 h-5 rounded-full shadow-[var(--shadow-extruded-sm)] border-4 border-[var(--color-clay)] ${item.color} z-10 shrink-0 mt-1`} />
                <div className="bg-[var(--color-clay)] p-4 rounded-2xl shadow-[var(--shadow-inset-sm)] flex-1 group-hover:shadow-[var(--shadow-inset-deep)] transition-shadow">
                  <div className="flex justify-between items-start mb-1">
                    <span className="font-bold text-sm text-[var(--color-primary)]">{item.id}</span>
                    <span className="text-xs text-[var(--color-muted)]">{item.time}</span>
                  </div>
                  <p className="text-sm text-[var(--color-muted)]">{item.action}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Live Agent Logs */}
        <Card className="p-8 flex flex-col">
          <h3 className="font-bold text-xl mb-6 flex items-center gap-2">
            <FileText className="w-5 h-5 text-[var(--color-accent)]" /> Live Agent Trace
          </h3>
          <div className="flex-1 bg-[#1e293b] rounded-2xl p-6 font-mono text-sm overflow-hidden relative shadow-[var(--shadow-inset-deep)] border border-[rgba(255,255,255,0.1)]">
            <div className="absolute top-0 left-0 w-full h-8 bg-gradient-to-b from-[#1e293b] to-transparent z-10" />
            <div className="space-y-3 text-gray-400">
              <p><span className="text-blue-400">[Supervisor]</span> Initializing CASE-8493 investigation...</p>
              <p><span className="text-green-400">[Document]</span> Extracting Invoice-990.pdf (Confidence: 98%)</p>
              <p><span className="text-green-400">[Document]</span> Found PO: PO-2026-9042</p>
              <p><span className="text-yellow-400">[Duplicate]</span> Querying ERP for vendor match...</p>
              <p><span className="text-purple-400">[Risk]</span> Checking OFAC DB for 'Acme Corp'...</p>
              <motion.p 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ repeat: Infinity, duration: 1.5, repeatType: 'reverse' }}
                className="text-white"
              >
                <span className="text-accent-400">[Policy]</span> Retrieving standard tolerance rules...
              </motion.p>
            </div>
            <div className="absolute bottom-0 left-0 w-full h-12 bg-gradient-to-t from-[#1e293b] to-transparent z-10" />
          </div>
        </Card>
      </div>      {/* Toast Notification */}
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
