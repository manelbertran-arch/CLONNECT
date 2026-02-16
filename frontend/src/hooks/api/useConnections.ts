import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getConnections, updateConnection, disconnectPlatform, apiKeys, getCreatorId } from "@/services/api";
import type { UpdateConnectionData } from "@/services/api";
import { useToast } from "@/hooks/use-toast";

export function useConnections(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: apiKeys.connections(creatorId), queryFn: () => getConnections(creatorId), staleTime: 60000 });
}

export function useUpdateConnection(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ platform, data }: { platform: string; data: UpdateConnectionData }) => updateConnection(creatorId, platform, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.connections(creatorId) }); queryClient.invalidateQueries({ queryKey: ["onboarding"] }); },
  });
}

const PLATFORM_NAMES: Record<string, string> = {
  instagram: "Instagram", telegram: "Telegram", whatsapp: "WhatsApp",
  stripe: "Stripe", paypal: "PayPal", hotmart: "Hotmart",
  calendly: "Calendly", zoom: "Zoom", google: "Google",
};

export function useDisconnectPlatform(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (platform: string) => disconnectPlatform(creatorId, platform),
    onSuccess: (_data, platform) => {
      queryClient.invalidateQueries({ queryKey: apiKeys.connections(creatorId) });
      queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      toast({ title: `${PLATFORM_NAMES[platform] || platform} desconectado`, description: "La conexion se ha eliminado correctamente." });
    },
    onError: (_error, platform) => {
      toast({ title: `Error al desconectar ${PLATFORM_NAMES[platform] || platform}`, description: "Intenta de nuevo.", variant: "destructive" });
    },
  });
}
