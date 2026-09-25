import { useState } from "react";
import { Camera, ScanLine, ShieldCheck } from "lucide-react";
import * as Tabs from "@radix-ui/react-tabs";
import { CaptureControl } from "@/features/capture/CaptureControl";
import { CameraCapture, type CameraStatus } from "./CameraCapture";
import { MonitorWatch } from "@/features/capture/MonitorWatch";
import { monitorIdle, type MonitorStatus } from "@/features/capture/monitor";

export function CameraWorkspace({ visible, patient, onStatus, onReview, onMonitorStatus }: {
  visible: boolean; patient: string; onStatus: (status: CameraStatus) => void; onReview: () => void;
  onMonitorStatus?: (status: MonitorStatus) => void;
}) {
  const [tab, setTab] = useState("watch");
  const [monitor, setMonitor] = useState(monitorIdle);
  return <section className="capture-workspace" aria-labelledby="capture-workspace-title">
    <header className="capture-workspace-heading">
      <span className="capture-heading-icon"><Camera size={23} aria-hidden /></span>
      <div><h1 id="capture-workspace-title">Capture visual evidence</h1><p><strong>{patient}</strong> · Watch for changes continuously, or capture a specific item.</p></div>
      <span className="capture-processing-label"><ShieldCheck size={16} aria-hidden />Processed on the vehicle</span>
    </header>
    <Tabs.Root value={tab} onValueChange={setTab} className="capture-workspace-tabs">
      <Tabs.List className="capture-methods" aria-label="Capture method">
        <Tabs.Trigger value="watch"><ScanLine size={18} aria-hidden />Monitor watch</Tabs.Trigger>
        <Tabs.Trigger value="photo" disabled={monitor.active || monitor.starting}><Camera size={18} aria-hidden />Take a photo</Tabs.Trigger>
        <Tabs.Trigger value="connected"><ScanLine size={18} aria-hidden />Connected camera</Tabs.Trigger>
      </Tabs.List>
      <Tabs.Content value="watch" forceMount hidden={tab !== "watch"} className="capture-method-content">
        <MonitorWatch onStatus={(status) => { setMonitor(status); onMonitorStatus?.(status); }} />
      </Tabs.Content>
      <Tabs.Content value="photo" forceMount hidden={tab !== "photo"} className="capture-method-content">
        <CameraCapture visible={visible && tab === "photo"} onStatus={onStatus} onReview={onReview} />
      </Tabs.Content>
      <Tabs.Content value="connected" className="capture-method-content"><CaptureControl /></Tabs.Content>
    </Tabs.Root>
  </section>;
}
