import { useState, useEffect } from "react";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";
import { apiPost } from "@/lib/api";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Loader2, AlertTriangle, PauseCircle, Trash2, SettingsIcon } from "lucide-react";
import { useAuthStore } from "@/features/auth/store/useAuthStore";

function redirectToLoggedOutHome() {
  useAuthStore.getState().logout();
  if (window.TAPNE_RUNTIME_CONFIG?.session) {
    (window.TAPNE_RUNTIME_CONFIG as any).session.authenticated = false;
    (window.TAPNE_RUNTIME_CONFIG as any).session.user = null;
  }
  window.location.assign("/");
}

const Settings = () => {
  const { isAuthenticated, requireAuth } = useAuth();
  const [emailNotif, setEmailNotif] = useState(true);
  const [pushNotif, setPushNotif] = useState(true);
  const [profilePublic, setProfilePublic] = useState(true);
  const [deactivateOpen, setDeactivateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      requireAuth(() => {});
    }
  }, [isAuthenticated, requireAuth]);

  const handleDeactivate = async () => {
    setPending(true);
    try {
      const cfg = window.TAPNE_RUNTIME_CONFIG;
      await apiPost(cfg.api.account_deactivate, {});
      toast.success("Account deactivated.");
      redirectToLoggedOutHome();
    } catch {
      toast.error("Could not deactivate account. Please try again.");
      setPending(false);
    }
  };

  const handleDelete = async () => {
    setPending(true);
    try {
      const cfg = window.TAPNE_RUNTIME_CONFIG;
      await apiPost(cfg.api.account_delete, {});
      toast.success("Account deleted.");
      redirectToLoggedOutHome();
    } catch {
      toast.error("Could not delete account. Please try again.");
      setPending(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <h1 className="mb-6 flex items-center gap-2 text-2xl font-bold text-foreground">
          <SettingsIcon className="h-6 w-6" />
          Settings
        </h1>

        <div className="space-y-6">
          <Card>
            <CardContent className="space-y-4 p-6">
              <h2 className="text-lg font-semibold">Notifications</h2>
              <div className="flex items-center justify-between">
                <Label>Email notifications</Label>
                <Switch checked={emailNotif} onCheckedChange={setEmailNotif} />
              </div>
              <div className="flex items-center justify-between">
                <Label>Push notifications</Label>
                <Switch checked={pushNotif} onCheckedChange={setPushNotif} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4 p-6">
              <h2 className="text-lg font-semibold">Privacy</h2>
              <div className="flex items-center justify-between">
                <div>
                  <Label>Public profile</Label>
                  <p className="text-xs text-muted-foreground">
                    Anyone can view your profile and trips.
                  </p>
                </div>
                <Switch checked={profilePublic} onCheckedChange={setProfilePublic} />
              </div>
            </CardContent>
          </Card>

          <Card className="border-destructive/30">
            <CardContent className="space-y-4 p-6">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-destructive">
                <AlertTriangle className="h-5 w-5" />
                Danger zone
              </h2>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => setDeactivateOpen(true)}>
                  <PauseCircle className="mr-1.5 h-4 w-4" />
                  Deactivate account
                </Button>
                <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
                  <Trash2 className="mr-1.5 h-4 w-4" />
                  Delete permanently
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
      <Footer />

      <AlertDialog open={deactivateOpen} onOpenChange={setDeactivateOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Deactivate account?</AlertDialogTitle>
            <AlertDialogDescription>
              Your profile will be hidden. You can reactivate by logging back in.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeactivate} disabled={pending}>
              {pending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Deactivate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete account permanently?</AlertDialogTitle>
            <AlertDialogDescription>
              This cannot be undone. All your trips, stories, and messages will be removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={pending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {pending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Delete permanently
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default Settings;
