import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface DeleteLeadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  leadName: string | undefined;
  onConfirm: () => void;
}

export function DeleteLeadDialog({
  open,
  onOpenChange,
  leadName,
  onConfirm,
}: DeleteLeadDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="sm:max-w-[340px]">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-base">Eliminar Lead</AlertDialogTitle>
          <AlertDialogDescription className="text-sm">
            ¿Eliminar a{" "}
            <span className="font-medium text-foreground">{leadName}</span>?
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="gap-2">
          <AlertDialogCancel className="h-8 text-xs">Cancelar</AlertDialogCancel>
          <Button
            onClick={onConfirm}
            className="h-8 text-xs bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            <Trash2 className="w-3.5 h-3.5 mr-1.5" />
            Eliminar
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
