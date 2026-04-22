import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

export default function UserNew() {
    const nav = useNavigate();
    const form = useForm({ mode: "onBlur", defaultValues: { user_type: "Internal", timezone: "Europe/London", locale: "en-GB" } });
    const [token, setToken] = useState(null);

    const onSubmit = async (values) => {
        try {
            const r = await api.post("/users", values);
            setToken(r.data.invitation_token);
            toast.success("User invited");
        } catch (e) {
            toast.error(e.friendlyMessage || "Failed to invite user");
        }
    };

    if (token) {
        return (
            <div className="max-w-2xl space-y-4" data-testid="invite-success">
                <h1 className="font-heading text-2xl font-bold">Invitation Sent</h1>
                <p className="text-sm text-slate-600">Share this one-time invitation token with the new user. It expires in 7 days.</p>
                <div className="bg-slate-900 text-white mono text-sm p-4 rounded-md break-all" data-testid="invite-token">{token}</div>
                <p className="text-xs text-amber-700">This token is shown once and cannot be retrieved — copy it now.</p>
                <Button onClick={() => nav("/users")} className="bg-slate-900 hover:bg-slate-800 text-white">Back to users</Button>
            </div>
        );
    }

    const Field = ({ label, name, type = "text", required, children }) => {
        const err = form.formState.errors[name];
        return (
            <div>
                <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">
                    {label} {required && <span className="text-rose-500">*</span>}
                </label>
                {children || <Input type={type} {...form.register(name, { required })} className="bg-white h-9" data-testid={`input-${name}`} />}
                {err && <div className="text-[11px] text-rose-600 mt-1">Required</div>}
            </div>
        );
    };

    return (
        <div className="space-y-6 max-w-3xl" data-testid="user-new-page">
            <div>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Users · Invite</div>
                <h1 className="font-heading text-3xl font-bold text-slate-900 mt-1">Invite a user</h1>
            </div>
            <form onSubmit={form.handleSubmit(onSubmit)} className="bg-white border border-slate-200 rounded-lg p-6 grid grid-cols-1 md:grid-cols-2 gap-5" data-testid="invite-form">
                <Field label="First name" name="first_name" required />
                <Field label="Last name" name="last_name" required />
                <Field label="Email" name="email" type="email" required />
                <Field label="Phone" name="phone" />
                <Field label="Job title" name="job_title" />
                <Field label="User type" name="user_type">
                    <select {...form.register("user_type")} className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" data-testid="input-user_type">
                        <option value="Internal">Internal</option>
                        <option value="External_Subcontractor">External subcontractor</option>
                        <option value="External_Consultant">External consultant</option>
                        <option value="External_Funder">External funder</option>
                        <option value="Service_Account">Service account</option>
                    </select>
                </Field>
                <Field label="Timezone" name="timezone" />
                <Field label="Locale" name="locale" />
                <div className="md:col-span-2">
                    <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Admin notes</label>
                    <Textarea {...form.register("admin_notes")} rows={3} className="bg-white" data-testid="input-admin_notes" />
                </div>
                <div className="md:col-span-2 flex justify-end gap-2 border-t border-slate-200 pt-4">
                    <Button type="button" variant="outline" onClick={() => nav("/users")} data-testid="invite-cancel">Cancel</Button>
                    <Button type="submit" className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="invite-submit">Send Invitation</Button>
                </div>
            </form>
        </div>
    );
}
