import { useState } from "react";
import { Camera, ScanLine, ShieldCheck } from "lucide-react";
import { Tabs } from "radix-ui";
import { CaptureControl } from "@/features/capture/CaptureControl";
import { CameraCapture, type CameraStatus } from "./CameraCapture";

export function CameraWorkspace({ visible, patient, onStatus, onReview }: {
  visible: boolean; patient: string; onStatus: (status: CameraStatus) => void; onReview: () => void;
}) {
  const [tab, setTab] = useState("photo");
  return <section className="capture-workspace" aria-labelledby="capture-workspace-title">
    <header className="capture-workspace-heading">
      <span className="capture-heading-icon"><Camera size={23} aria-hidden /></span>
      <div><h1 id="capture-workspace-title">Capture visual evidence</h1><p><strong>{patient}</strong> · Capture an image, then verify the extracted information.</p></div>
      <span className="capture-processing-label"><ShieldCheck size={16} aria-hidden />Processed on the vehicle</span>
    </header>
    <Tabs.Root value={tab} onValueChange={setTab} className="capture-workspace-tabs">
      <Tabs.List className="capture-methods" aria-label="Capture method">
        <Tabs.Trigger value="photo"><Camera size={18} aria-hidden />Take a photo</Tabs.Trigger>
        <Tabs.Trigger value="connected"><ScanLine size={18} aria-hidden />Connected camera</Tabs.Trigger>
      </Tabs.List>
      <Tabs.Content value="photo" forceMount hidden={tab !== "photo"} className="capture-method-content">
        <CameraCapture visible={visible && tab === "photo"} onStatus={onStatus} onReview={onReview} />
      </Tabs.Content>
      <Tabs.Content value="connected" className="capture-method-content"><CaptureControl /></Tabs.Content>
    </Tabs.Root>
  </section>;
}
