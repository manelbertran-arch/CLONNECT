import { useState } from "react";
import { Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface AddLeadFormData {
  name: string;
  platform: string;
  email: string;
  phone: string;
  notes: string;
}

interface AddLeadModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isPending: boolean;
  onSubmit: (data: AddLeadFormData) => void;
}

const initialFormState: AddLeadFormData = {
  name: "",
  platform: "instagram",
  email: "",
  phone: "",
  notes: "",
};

export function AddLeadModal({ open, onOpenChange, isPending, onSubmit }: AddLeadModalProps) {
  const [formData, setFormData] = useState<AddLeadFormData>(initialFormState);

  const handleSubmit = () => {
    onSubmit(formData);
    setFormData(initialFormState);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) setFormData(initialFormState);
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[380px]">
        <DialogHeader>
          <DialogTitle className="text-base">Nuevo Lead</DialogTitle>
          <DialogDescription className="text-xs">
            Agrega un lead manualmente
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 py-3">
          <div className="grid gap-1.5">
            <Label htmlFor="name" className="text-xs">Nombre *</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="Nombre del contacto"
              className="h-9"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="platform" className="text-xs">Plataforma</Label>
            <Select
              value={formData.platform}
              onValueChange={(value) => setFormData({ ...formData, platform: value })}
            >
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Seleccionar" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="instagram">Instagram</SelectItem>
                <SelectItem value="telegram">Telegram</SelectItem>
                <SelectItem value="whatsapp">WhatsApp</SelectItem>
                <SelectItem value="manual">Otro</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="email" className="text-xs">Email</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="email@ejemplo.com"
                className="h-9"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="phone" className="text-xs">Teléfono</Label>
              <Input
                id="phone"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                placeholder="+34 600..."
                className="h-9"
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="notes" className="text-xs">Notas</Label>
            <Input
              id="notes"
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Notas adicionales..."
              className="h-9"
            />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="ghost" size="sm" onClick={() => handleOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={handleSubmit} disabled={isPending} size="sm">
            {isPending ? (
              <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
            ) : (
              <Plus className="w-3.5 h-3.5 mr-1.5" />
            )}
            Agregar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export type { AddLeadFormData };
