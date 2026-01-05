import { Outlet } from 'react-router-dom';
import { NewNavigation } from './NewNavigation';

export function NewLayout() {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <NewNavigation />

      {/* Main content */}
      <main className="pb-20 md:pb-0 md:pl-20">
        <div className="max-w-4xl mx-auto p-4 md:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
