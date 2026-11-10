import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronLeft, ChevronRight, Download, MousePointer2, Pause, Play, Printer, RotateCcw, Wifi } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SCENE_MS = 7000;

type Scene = { title: string; caption: string; body: React.ReactNode };

/** Animated cursor that travels to a target spot and "clicks" there. */
function Cursor({ x, y, delay = 0.8 }: { x: string; y: string; delay?: number }) {
  return (
    <motion.div className="pointer-events-none absolute z-20" initial={{ left: "85%", top: "85%" }} animate={{ left: x, top: y }} transition={{ delay, duration: 1.2, ease: "easeInOut" }}>
      <motion.div animate={{ scale: [1, 0.8, 1] }} transition={{ delay: delay + 1.3, duration: 0.3 }}>
        <MousePointer2 className="size-6 fill-white text-ink drop-shadow" />
      </motion.div>
    </motion.div>
  );
}

function WinWindow({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("overflow-hidden rounded-lg border border-slate-300 bg-white shadow-xl", className)}>
      <div className="flex items-center justify-between bg-slate-100 px-3 py-1.5 text-[11px] text-slate-600">
        <span className="font-semibold">{title}</span>
        <span className="tracking-[0.3em]">— ▢ ✕</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

const scenes: Scene[] = [
  {
    title: "1. Télécharger",
    caption: "Sur le PC du comptoir, ouvrez cette page et cliquez sur « Télécharger l'agent Windows ».",
    body: (
      <div className="relative h-full p-6">
        <div className="rounded-xl border bg-white p-4 shadow-sm">
          <p className="text-sm font-semibold text-ink">Installer l'agent Windows</p>
          <p className="mt-1 text-xs text-slate-500">Windows 10/11</p>
          <motion.div className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-azure px-3 py-2 text-xs font-semibold text-white"
            animate={{ scale: [1, 1, 0.94, 1] }} transition={{ delay: 2, duration: 0.4 }}>
            <Download className="size-3.5" /> Télécharger l'agent Windows
          </motion.div>
        </div>
        <motion.div className="absolute right-6 bottom-6 flex items-center gap-2 rounded-lg border bg-white px-3 py-2 text-xs shadow-lg"
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 2.8 }}>
          <Download className="size-4 text-azure" /> PrintDrop-Setup.exe <span className="text-emerald-600">✓ téléchargé</span>
        </motion.div>
        <Cursor x="22%" y="58%" />
      </div>
    ),
  },
  {
    title: "2. Installer",
    caption: "Ouvrez le fichier. Si Windows affiche un avertissement : « Informations complémentaires » puis « Exécuter quand même ». Laissez cochée « Démarrer avec Windows ».",
    body: (
      <div className="relative flex h-full items-center justify-center p-6">
        <WinWindow title="Installation — PrintDrop pour Windows" className="w-[min(100%,380px)]">
          <p className="text-xs font-semibold text-ink">Tâches supplémentaires</p>
          <label className="mt-2 flex items-center gap-2 text-xs"><span className="flex size-4 items-center justify-center rounded-sm border bg-azure text-white"><Check className="size-3" /></span>Démarrer PrintDrop automatiquement avec Windows</label>
          <label className="mt-1 flex items-center gap-2 text-xs text-slate-500"><span className="size-4 rounded-sm border" />Créer un raccourci sur le Bureau</label>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200">
            <motion.div className="h-full bg-emerald-500" initial={{ width: "0%" }} animate={{ width: "100%" }} transition={{ delay: 2.4, duration: 3, ease: "easeInOut" }} />
          </div>
          <motion.p className="mt-2 text-[11px] text-emerald-700" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 5.5 }}>Installation terminée</motion.p>
        </WinWindow>
        <Cursor x="62%" y="78%" delay={0.6} />
      </div>
    ),
  },
  {
    title: "3. Associer le PC",
    caption: "PrintDrop s'ouvre. Ici, cliquez sur « Générer un code d'appairage », puis saisissez ce code dans la fenêtre PrintDrop du PC.",
    body: (
      <div className="relative grid h-full grid-cols-2 items-center gap-4 p-6">
        <div className="rounded-xl bg-ink p-4 text-center text-white shadow-lg">
          <p className="text-[11px] text-slate-300">Code d'appairage</p>
          <motion.p className="mt-1 font-mono text-2xl font-bold tracking-[0.2em]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1 }}>K7Q2M9</motion.p>
        </div>
        <WinWindow title="PrintDrop">
          <p className="text-xs text-slate-600">Code d'appairage</p>
          <div className="mt-1 rounded border px-2 py-1.5 font-mono text-sm tracking-[0.2em]">
            {"K7Q2M9".split("").map((c, i) => (
              <motion.span key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2 + i * 0.25 }}>{c}</motion.span>
            ))}
          </div>
          <motion.p className="mt-3 flex items-center gap-1 text-xs font-semibold text-emerald-700" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 4.4 }}>
            <Check className="size-3.5" /> Poste associé à votre boutique
          </motion.p>
        </WinWindow>
      </div>
    ),
  },
  {
    title: "4. Ajouter une imprimante",
    caption: "Cliquez sur « Ajouter une imprimante » puis « Rechercher les imprimantes ». Choisissez la vôtre et cliquez sur « Connecter cette imprimante ».",
    body: (
      <div className="relative h-full space-y-2 p-6">
        {[{ n: "HP LaserJet MFP (USB)", icon: <Printer className="size-4 text-azure" />, d: 0.8 }, { n: "EPSON ET-2850 (Wi-Fi)", icon: <Wifi className="size-4 text-azure" />, d: 1.2 }].map((r, i) => (
          <motion.div key={r.n} className="flex items-center gap-3 rounded-xl border bg-white p-3 text-xs shadow-sm" initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: r.d }}>
            {r.icon}<span className="flex-1 font-semibold text-ink">{r.n}</span>
            {i === 0 ? (
              <motion.span className="rounded-md bg-azure px-2 py-1 font-semibold text-white" animate={{ backgroundColor: ["#0b6bff", "#0b6bff", "#059669"] }} transition={{ delay: 3.2, duration: 0.6 }}>
                <motion.span initial={{ opacity: 1 }} animate={{ opacity: 1 }}>Connecter</motion.span>
              </motion.span>
            ) : <span className="rounded-md border px-2 py-1 text-slate-500">Connecter</span>}
          </motion.div>
        ))}
        <motion.p className="flex items-center gap-1.5 pt-2 text-sm font-semibold text-emerald-700" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 4 }}>
          <Check className="size-4" /> HP LaserJet MFP : Prête
        </motion.p>
        <Cursor x="82%" y="22%" delay={1.6} />
      </div>
    ),
  },
];

/** « Guide vidéo » — animated walkthrough (not a screen recording) of download → install → pairing → add printer. */
export function AgentSetupGuide() {
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [run, setRun] = useState(0); // restarts the scene animation
  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => {
      if (i === scenes.length - 1) setPlaying(false);
      else { setI(i + 1); setRun((r) => r + 1); }
    }, SCENE_MS);
    return () => clearTimeout(t);
  }, [playing, i, run]);
  const go = (n: number) => { setI(n); setRun((r) => r + 1); };
  const s = scenes[i];
  return (
    <section className="overflow-hidden rounded-2xl border bg-card" data-testid="agent-setup-guide">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b p-5">
        <div>
          <h2 className="text-lg font-semibold text-ink">Guide vidéo : installer PrintDrop en 2 minutes</h2>
          <p className="text-xs text-muted-foreground">Animation pas à pas : téléchargement, installation, appairage, ajout d'une imprimante.</p>
        </div>
        <Button size="sm" onClick={() => { if (!playing && i === scenes.length - 1) go(0); setPlaying(!playing); }} data-testid="guide-play">
          {playing ? <><Pause className="size-3.5" /> Pause</> : i === scenes.length - 1 && run > 0 ? <><RotateCcw className="size-3.5" /> Revoir</> : <><Play className="size-3.5" /> Lire le guide</>}
        </Button>
      </div>
      <div className="relative aspect-[16/8] bg-gradient-to-br from-slate-100 to-sky-50" data-testid="guide-stage">
        <AnimatePresence mode="wait">
          <motion.div key={`${i}-${run}-${playing}`} className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            {playing || run > 0 ? s.body : (
              <button type="button" onClick={() => setPlaying(true)} className="flex size-full flex-col items-center justify-center gap-3 text-ink" data-testid="guide-poster">
                <span className="flex size-16 items-center justify-center rounded-full bg-azure text-white shadow-lg transition-transform duration-200 hover:scale-105"><Play className="ml-1 size-7" /></span>
                <span className="text-sm font-semibold">Voir comment installer PrintDrop</span>
              </button>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="space-y-3 p-5">
        <div className="flex gap-1.5" data-testid="guide-progress">
          {scenes.map((sc, n) => (
            <button key={sc.title} type="button" onClick={() => go(n)} className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200" aria-label={sc.title} data-testid={`guide-step-${n}`}>
              {n < i && <span className="block h-full w-full bg-azure" />}
              {n === i && (playing
                ? <motion.span key={`${run}`} className="block h-full bg-azure" initial={{ width: "0%" }} animate={{ width: "100%" }} transition={{ duration: SCENE_MS / 1000, ease: "linear" }} />
                : <span className="block h-full w-1/2 bg-azure/60" />)}
            </button>
          ))}
        </div>
        <div className="flex items-start gap-3">
          <Button size="icon" variant="outline" disabled={i === 0} onClick={() => go(i - 1)} aria-label="Étape précédente" data-testid="guide-prev"><ChevronLeft className="size-4" /></Button>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink" data-testid="guide-title">{s.title}</p>
            <p className="text-sm text-muted-foreground" data-testid="guide-caption">{s.caption}</p>
          </div>
          <Button size="icon" variant="outline" disabled={i === scenes.length - 1} onClick={() => go(i + 1)} aria-label="Étape suivante" data-testid="guide-next"><ChevronRight className="size-4" /></Button>
        </div>
      </div>
    </section>
  );
}
