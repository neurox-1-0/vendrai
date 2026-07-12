import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { IconWell } from '@/components/ui/icon-well';
import { ShieldCheck, FileText, Search, Activity, Users, Settings, Bell, LayoutDashboard } from 'lucide-react';

export default function Dashboard() {
  return (
    <div className="flex h-screen overflow-hidden text-[var(--color-primary)]">
      {/* Sidebar */}
      <aside className="w-64 flex flex-col justify-between p-8 border-r border-[rgba(255,255,255,0.2)] shadow-[var(--shadow-extruded)] z-10 relative">
        <div>
          <div className="flex justify-center mb-16">
            <img src="/Full logo.svg" alt="Vendrai Logo" className="h-24 w-24 object-cover rounded-3xl shadow-[var(--shadow-extruded)]" />
          </div>
          
          <nav className="space-y-4">
            <Button variant="secondary" className="w-full justify-start gap-4">
              <LayoutDashboard className="h-5 w-5" /> Dashboard
            </Button>
            <Button variant="secondary" className="w-full justify-start gap-4 opacity-70 hover:opacity-100">
              <FileText className="h-5 w-5" /> Cases
            </Button>
            <Button variant="secondary" className="w-full justify-start gap-4 opacity-70 hover:opacity-100">
              <Users className="h-5 w-5" /> Vendors
            </Button>
            <Button variant="secondary" className="w-full justify-start gap-4 opacity-70 hover:opacity-100">
              <Activity className="h-5 w-5" /> Analytics
            </Button>
          </nav>
        </div>
        
        <Button variant="icon" className="mx-auto w-12 h-12">
          <Settings className="h-5 w-5" />
        </Button>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full overflow-y-auto">
        {/* Header */}
        <header className="h-24 flex items-center justify-between px-12 z-0">
          <h2 className="font-display font-bold text-3xl">Active Overview</h2>
          
          <div className="flex items-center gap-8">
            <div className="relative w-80">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-[var(--color-muted)]" />
              <Input placeholder="Search cases or vendors..." className="pl-12" />
            </div>
            
            <Button variant="icon" className="relative">
              <Bell className="h-5 w-5" />
              <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full"></span>
            </Button>
            
            <div className="h-12 w-12 rounded-full shadow-[var(--shadow-extruded)] border-2 border-[var(--color-clay)] overflow-hidden">
              <img src="/user-image.jpg" alt="User Avatar" className="h-full w-full object-cover" />
            </div>
          </div>
        </header>

        {/* Dashboard Grid */}
        <div className="p-12 pt-4 grid grid-cols-1 lg:grid-cols-3 gap-12">
          
          {/* Main Chart Card */}
          <Card className="lg:col-span-2 min-h-[400px] flex flex-col justify-between">
            <div className="flex justify-between items-start mb-8">
              <div>
                <h3 className="font-bold text-xl mb-2">Exceptions Volume</h3>
                <p className="text-[var(--color-muted)]">Real-time processing metrics</p>
              </div>
              <Button variant="primary">Generate Report</Button>
            </div>
            
            <div className="flex-1 rounded-2xl shadow-[var(--shadow-inset-deep)] bg-[var(--color-clay)] relative overflow-hidden flex items-end justify-between p-8">
              {/* Fake Chart Bars for Neumorphic Visuals */}
              <div className="w-16 h-24 rounded-t-xl bg-[var(--color-clay)] shadow-[var(--shadow-extruded)]"></div>
              <div className="w-16 h-48 rounded-t-xl bg-[var(--color-clay)] shadow-[var(--shadow-extruded)]"></div>
              <div className="w-16 h-32 rounded-t-xl bg-[var(--color-clay)] shadow-[var(--shadow-extruded)]"></div>
              <div className="w-16 h-64 rounded-t-xl bg-[var(--color-accent)] shadow-[var(--shadow-extruded)]"></div>
              <div className="w-16 h-56 rounded-t-xl bg-[var(--color-clay)] shadow-[var(--shadow-extruded)]"></div>
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
                <div className="h-full bg-[var(--color-accent)] w-[60%] rounded-full shadow-[var(--shadow-extruded-sm)]"></div>
              </div>
            </Card>
            
            <Card className="p-8">
              <h3 className="font-bold text-xl mb-6">Agent Status</h3>
              <div className="space-y-6">
                <div className="flex justify-between items-center">
                  <span className="font-medium text-[var(--color-muted)]">Document Extraction</span>
                  <span className="h-3 w-3 bg-green-400 rounded-full shadow-[var(--shadow-extruded-sm)]"></span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="font-medium text-[var(--color-muted)]">Duplicate Review</span>
                  <span className="h-3 w-3 bg-[var(--color-accent)] rounded-full shadow-[var(--shadow-extruded-sm)] animate-pulse"></span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="font-medium text-[var(--color-muted)]">Risk Analysis</span>
                  <span className="h-3 w-3 bg-green-400 rounded-full shadow-[var(--shadow-extruded-sm)]"></span>
                </div>
              </div>
            </Card>
          </div>
          
        </div>
      </main>
    </div>
  );
}
