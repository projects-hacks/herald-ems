import { useEffect, useState } from "react";
import { Wifi, WifiOff } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

/** Browser-reported internet availability; clinical relay status remains in the ED card. */
export function NetworkStatus() {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);
  const label = online ? "Connected to the internet" : "No internet connection";
  const Icon = online ? Wifi : WifiOff;

  return <TooltipProvider delayDuration={300}>
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="network-status" data-state={online ? "online" : "offline"} role="status" aria-label={label} tabIndex={0}>
          <Icon size={19} aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={6}>{label}</TooltipContent>
    </Tooltip>
  </TooltipProvider>;
}
