import { Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import DashboardLayout from "@/components/DashboardLayout";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import CustomerPortal from "@/pages/CustomerPortal";
import Tracking from "@/pages/Tracking";
import SuperAdmin from "@/pages/SuperAdmin";
import Orders from "@/pages/dashboard/Orders";
import Pricing from "@/pages/dashboard/Pricing";
import ShopSettings from "@/pages/dashboard/ShopSettings";
import Team from "@/pages/dashboard/Team";
import Audit from "@/pages/dashboard/Audit";
import Devices from "@/pages/dashboard/Devices";
import Reports from "@/pages/dashboard/Reports";
import Billing from "@/pages/dashboard/Billing";
import PrintQueue, { Onboarding } from "@/pages/dashboard/PrintQueue";
import InvoicePage from "@/pages/dashboard/Invoice";
import { BrandPreview } from "@/components/brand/BrandPreview";
import LandingV2 from "@/pages/site/LandingV2";
import Contact from "@/pages/site/Contact";
import LegalPage from "@/pages/site/Legal";

// One <Route> per page in src/pages; BrowserRouter already wraps this in main.tsx.
export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/connexion" element={<Login />} />
        <Route path="/inscription" element={<Register />} />
        <Route path="/s/:slug" element={<CustomerPortal />} />
        <Route path="/suivi" element={<Tracking />} />
        <Route path="/suivi/:code" element={<Tracking />} />
        <Route path="/superadmin" element={<SuperAdmin />} />
        <Route path="/dashboard" element={<DashboardLayout />}>
          <Route index element={<Orders />} />
          <Route path="tarifs" element={<Pricing />} />
          <Route path="boutique" element={<ShopSettings />} />
          <Route path="rapports" element={<Reports />} />
          <Route path="abonnement" element={<Billing />} />
          <Route path="file-impression" element={<PrintQueue />} />
          <Route path="demarrage" element={<Onboarding />} />
          <Route path="abonnement/facture/:id" element={<InvoicePage />} />
          <Route path="imprimantes" element={<Devices />} />
          <Route path="equipe" element={<Team />} />
          <Route path="journal" element={<Audit />} />
        </Route>
        {/* Brand v2 preview (Stage 3) — real pages rendered with the official identity, live routes untouched */}
        <Route path="/apercu" element={<BrandPreview />}>
          <Route index element={<LandingV2 />} />
          <Route path="connexion" element={<Login />} />
          <Route path="contact" element={<Contact />} />
          <Route path="s/:slug" element={<CustomerPortal />} />
          <Route path="dashboard" element={<DashboardLayout />}>
            <Route index element={<Orders />} />
          </Route>
          <Route path=":doc" element={<LegalPage />} />
        </Route>
        <Route path="*" element={<Landing />} />
      </Routes>
      <Toaster richColors />
    </>
  );
}
