import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, Link2, Loader2, AlertCircle, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";

import { useCreatorConfig, useProducts, useUpdateConfig, useAddProduct, useUpdateProduct, useDeleteProduct, useKnowledge, useAddFAQ, useDeleteFAQ, useUpdateFAQ, useUpdateAbout, useConnections, useUpdateConnection, useDisconnectPlatform } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import type { Product } from "@/types/api";
import PersonalityTab from "@/components/settings/PersonalityTab";
import ConnectionsTab from "@/components/settings/ConnectionsTab";
import KnowledgeTab from "@/components/settings/KnowledgeTab";

interface ProductFormData {
  name: string;
  description: string;
  price: number;
  currency: string;
  payment_link: string;
  is_active: boolean;
}

const emptyProduct: ProductFormData = {
  name: "",
  description: "",
  price: 0,
  currency: "EUR",
  payment_link: "",
  is_active: true,
};

export default function Settings() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const tabFromUrl = searchParams.get("tab") || "personality";
  const [activeTab, setActiveTab] = useState(tabFromUrl);

  const { data: configData, isLoading: configLoading, error: configError } = useCreatorConfig();
  const { data: productsData } = useProducts();
  const updateConfig = useUpdateConfig();
  const addProductMutation = useAddProduct();
  const updateProductMutation = useUpdateProduct();
  const deleteProductMutation = useDeleteProduct();
  const { data: knowledgeData, isLoading: knowledgeLoading } = useKnowledge();
  const addFAQMutation = useAddFAQ();
  const deleteFAQMutation = useDeleteFAQ();
  const updateFAQMutation = useUpdateFAQ();

  const updateAboutMutation = useUpdateAbout();
  const { data: connectionsData, isLoading: connectionsLoading } = useConnections();
  const updateConnectionMutation = useUpdateConnection();
  const disconnectMutation = useDisconnectPlatform();
  const { toast } = useToast();

  const config = configData?.config;

  // Product modal state
  const [productModalOpen, setProductModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [productForm, setProductForm] = useState<ProductFormData>(emptyProduct);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [productToDelete, setProductToDelete] = useState<Product | null>(null);

  const handleSaveProduct = async () => {
    try {
      if (editingProduct) {
        await updateProductMutation.mutateAsync({
          productId: editingProduct.id,
          product: productForm,
        });
        toast({ title: "Product updated", description: `${productForm.name} has been updated.` });
      } else {
        await addProductMutation.mutateAsync(productForm as Omit<Product, "id">);
        toast({ title: "Product added", description: `${productForm.name} has been created.` });
      }
      setProductModalOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      navigate("/");
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to save product",
        variant: "destructive",
      });
    }
  };

  const handleDeleteProduct = async () => {
    if (!productToDelete) return;
    try {
      await deleteProductMutation.mutateAsync(productToDelete.id);
      toast({ title: "Product deleted", description: `${productToDelete.name} has been removed.` });
      setDeleteConfirmOpen(false);
      setProductToDelete(null);
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to delete product",
        variant: "destructive",
      });
    }
  };

  // Loading state — skeleton
  if (configLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div>
          <div className="h-7 w-28 bg-muted/40 rounded mb-2" />
          <div className="h-4 w-56 bg-muted/30 rounded" />
        </div>
        <div className="flex gap-2">
          {[1, 2, 3, 4].map(i => <div key={i} className="h-9 w-24 bg-muted/20 rounded-lg" />)}
        </div>
        <div className="space-y-4">
          <div className="p-6 rounded-2xl bg-muted/15 border border-border/20">
            <div className="h-5 w-32 bg-muted/30 rounded mb-4" />
            <div className="space-y-3">
              <div className="h-10 bg-muted/20 rounded-lg" />
              <div className="h-10 bg-muted/20 rounded-lg" />
              <div className="h-24 bg-muted/20 rounded-lg" />
            </div>
          </div>
          <div className="p-6 rounded-2xl bg-muted/15 border border-border/20">
            <div className="h-5 w-40 bg-muted/30 rounded mb-4" />
            <div className="h-32 bg-muted/20 rounded-lg" />
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (configError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-muted-foreground">Error al cargar ajustes</p>
        <p className="text-sm text-destructive">{configError.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ajustes</h1>
        <p className="text-sm text-muted-foreground">Configuración del bot</p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
          <TabsList className="bg-card border border-border/50 p-1 rounded-xl w-max sm:w-auto">
            <TabsTrigger value="personality" className="rounded-lg data-[state=active]:bg-muted text-xs sm:text-sm">
              <Bot className="w-4 h-4 mr-1 sm:mr-2" />
              <span className="hidden sm:inline">Personalidad</span>
              <span className="sm:hidden">Bot</span>
            </TabsTrigger>
            <TabsTrigger value="connections" className="rounded-lg data-[state=active]:bg-muted text-xs sm:text-sm">
              <Link2 className="w-4 h-4 mr-1 sm:mr-2" />
              <span className="hidden sm:inline">Conexiones</span>
              <span className="sm:hidden">Links</span>
            </TabsTrigger>
            <TabsTrigger value="knowledge" className="rounded-lg data-[state=active]:bg-muted text-xs sm:text-sm">
              <BookOpen className="w-4 h-4 mr-1 sm:mr-2" />
              <span className="hidden sm:inline">Conocimiento</span>
              <span className="sm:hidden">KB</span>
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Personality Tab */}
        <TabsContent value="personality" className="space-y-6 animate-fade-in">
          <PersonalityTab
            config={config}
            updateConfig={updateConfig}
            toast={toast}
            queryClient={queryClient}
          />
        </TabsContent>

        {/* Connections Tab */}
        <TabsContent value="connections" className="animate-fade-in">
          <ConnectionsTab
            config={config}
            connectionsData={connectionsData}
            connectionsLoading={connectionsLoading}
            updateConnectionMutation={updateConnectionMutation}
            disconnectMutation={disconnectMutation}
            toast={toast}
            queryClient={queryClient}
            updateConfig={updateConfig}
          />
        </TabsContent>

        {/* Knowledge Tab */}
        <TabsContent value="knowledge" className="animate-fade-in space-y-6">
          <KnowledgeTab
            knowledgeData={knowledgeData}
            knowledgeLoading={knowledgeLoading}
            productsData={productsData}
            toast={toast}
            addFAQMutation={addFAQMutation}
            deleteFAQMutation={deleteFAQMutation}
            updateFAQMutation={updateFAQMutation}
            updateAboutMutation={updateAboutMutation}
          />
        </TabsContent>
      </Tabs>

      {/* Product Modal */}
      <Dialog open={productModalOpen} onOpenChange={setProductModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingProduct ? "Edit Product" : "Add New Product"}</DialogTitle>
            <DialogDescription>
              {editingProduct ? "Update product details" : "Create a new product for your bot to recommend"}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="productName">Product Name</Label>
              <Input
                id="productName"
                value={productForm.name}
                onChange={(e) => setProductForm({ ...productForm, name: e.target.value })}
                placeholder="e.g., Premium Coaching Program"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="productDescription">Description</Label>
              <Textarea
                id="productDescription"
                value={productForm.description}
                onChange={(e) => setProductForm({ ...productForm, description: e.target.value })}
                placeholder="Brief description of the product..."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="productPrice">Price</Label>
                <Input
                  id="productPrice"
                  type="number"
                  value={productForm.price}
                  onChange={(e) => setProductForm({ ...productForm, price: Number(e.target.value) })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="productCurrency">Currency</Label>
                <Select
                  value={productForm.currency}
                  onValueChange={(v) => setProductForm({ ...productForm, currency: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="EUR">EUR (€)</SelectItem>
                    <SelectItem value="USD">USD ($)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="productUrl">Payment Link</Label>
              <Input
                id="productUrl"
                value={productForm.payment_link}
                onChange={(e) => setProductForm({ ...productForm, payment_link: e.target.value })}
                placeholder="https://stripe.com/pay/..."
              />
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="productActive">Active</Label>
              <Switch
                id="productActive"
                checked={productForm.is_active}
                onCheckedChange={(v) => setProductForm({ ...productForm, is_active: v })}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setProductModalOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSaveProduct}
              disabled={!productForm.name || addProductMutation.isPending || updateProductMutation.isPending}
            >
              {(addProductMutation.isPending || updateProductMutation.isPending) && (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              )}
              {editingProduct ? "Save Changes" : "Add Product"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Product</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{productToDelete?.name}"? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteProduct}
              disabled={deleteProductMutation.isPending}
            >
              {deleteProductMutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
