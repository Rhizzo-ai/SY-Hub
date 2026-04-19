import React from "react";
import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import AppShell from "@/components/AppShell";
import EntitiesList from "@/pages/EntitiesList";
import EntityDetail from "@/pages/EntityDetail";
import EntityNew from "@/pages/EntityNew";
import EntityEdit from "@/pages/EntityEdit";

function App() {
    return (
        <div className="App">
            <BrowserRouter>
                <AppShell>
                    <Routes>
                        <Route path="/" element={<Navigate to="/entities" replace />} />
                        <Route path="/entities" element={<EntitiesList />} />
                        <Route path="/entities/new" element={<EntityNew />} />
                        <Route path="/entities/:id" element={<EntityDetail />} />
                        <Route path="/entities/:id/edit" element={<EntityEdit />} />
                        <Route
                            path="*"
                            element={
                                <div className="text-slate-600" data-testid="not-found-page">
                                    <h1 className="font-heading text-2xl font-bold text-slate-900">
                                        Not found
                                    </h1>
                                    <p className="text-sm mt-2">
                                        This module is not yet available in Phase 1.
                                    </p>
                                </div>
                            }
                        />
                    </Routes>
                </AppShell>
                <Toaster
                    position="top-right"
                    toastOptions={{
                        className: "!font-sans",
                    }}
                />
            </BrowserRouter>
        </div>
    );
}

export default App;
