import React from "react";
import { AlertTriangle, ShieldCheck, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ConfirmationModalProps {
  toolName: string;
  onAccept: () => void;
  onReject: () => void;
  isConfirming: boolean;
}

const friendlyToolNames: Record<string, { title: string; description: string }> = {
  create_refund_request: {
    title: "Process Refund Request",
    description: "The AI agent wants to initiate a refund for the specified transaction.",
  },
  update_customer_details: {
    title: "Update Personal Details",
    description: "The AI agent wants to update your verified account profile information.",
  },
};

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  toolName,
  onAccept,
  onReject,
  isConfirming,
}) => {
  const toolInfo = friendlyToolNames[toolName] || {
    title: (toolName || "Sensitive Action").replace(/_/g, " "),
    description: "This agentic action requires your explicit confirmation before execution.",
  };

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-card text-card-foreground rounded-2xl shadow-2xl border border-border w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="px-6 py-5 border-b border-warning/20 flex items-center gap-3 bg-warning/10">
          <div className="w-10 h-10 rounded-full bg-warning/20 flex items-center justify-center text-warning shrink-0">
            <AlertTriangle className="size-5" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-foreground">Action Authorization Required</h3>
            <p className="text-xs text-muted-foreground">{toolInfo.title}</p>
          </div>
        </div>

        <div className="p-6 space-y-4">
          <p className="text-sm text-muted-foreground leading-relaxed">
            The AI agent has requested permission to execute the following operation on your behalf:
          </p>

          <div className="bg-muted/50 p-4 rounded-xl border border-border space-y-2">
            <div>
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Operation</span>
              <p className="text-sm font-medium text-foreground capitalize">{toolInfo.title}</p>
            </div>
            <div>
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Details</span>
              <p className="text-xs text-muted-foreground leading-relaxed">{toolInfo.description}</p>
            </div>
          </div>

          <p className="text-xs text-muted-foreground italic flex items-center gap-1.5">
            <ShieldCheck className="size-3.5 text-primary" />
            No changes will take effect without your authorization.
          </p>
        </div>

        <div className="px-6 py-4 bg-muted/30 border-t border-border flex justify-end gap-3">
          <Button
            variant="outline"
            onClick={onReject}
            disabled={isConfirming}
          >
            Reject
          </Button>
          <Button
            onClick={onAccept}
            disabled={isConfirming}
            className="bg-warning text-warning-foreground hover:bg-warning/90 font-medium"
          >
            {isConfirming ? <Loader2 className="size-4 animate-spin mr-1.5" /> : null}
            Authorize Action
          </Button>
        </div>
      </div>
    </div>
  );
};
