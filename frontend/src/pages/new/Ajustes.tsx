import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { getCreatorConfig, getConnections, getProducts, getBookingLinks, CREATOR_ID } from '@/services/api';
import {
  Package,
  CreditCard,
  Link2,
  Calendar,
  Bot,
  ChevronRight,
  Zap,
} from 'lucide-react';

// Sub-components for each section
import ProductoSection from './ajustes/ProductoSection';
import PagosSection from './ajustes/PagosSection';
import ConexionesSection from './ajustes/ConexionesSection';
import CalendarioSection from './ajustes/CalendarioSection';
import AutomatizacionesSection from './ajustes/AutomatizacionesSection';
import TuClonSection from './ajustes/TuClonSection';

type Section =
  | 'main'
  | 'producto'
  | 'pagos'
  | 'conexiones'
  | 'calendario'
  | 'automatizaciones'
  | 'clon';

export default function Ajustes() {
  const [searchParams, setSearchParams] = useSearchParams();
  const section = (searchParams.get('section') as Section) || 'main';
  const creatorId = CREATOR_ID;

  const { data: configData } = useQuery({
    queryKey: ['config', creatorId],
    queryFn: () => getCreatorConfig(creatorId),
  });

  const { data: connectionsData } = useQuery({
    queryKey: ['connections', creatorId],
    queryFn: () => getConnections(creatorId),
  });

  const { data: productsData } = useQuery({
    queryKey: ['products', creatorId],
    queryFn: () => getProducts(creatorId),
  });

  const { data: bookingLinksData } = useQuery({
    queryKey: ['bookingLinks', creatorId],
    queryFn: () => getBookingLinks(creatorId),
  });

  const config = configData?.config;
  const connections = connectionsData;
  const products = productsData?.products || [];
  const bookingLinks = bookingLinksData?.links || [];

  const setSection = (s: Section) => {
    if (s === 'main') {
      setSearchParams({});
    } else {
      setSearchParams({ section: s });
    }
  };

  // Handle OAuth callback: show success and navigate to conexiones
  useEffect(() => {
    if (searchParams.get('instagram') === 'connected') {
      toast.success('Instagram conectado correctamente');
      setSection('conexiones');
      setSearchParams({ section: 'conexiones' });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Build connections summary
  const connectedPlatforms = [
    connections?.instagram?.connected && 'Instagram',
    connections?.telegram?.connected && 'Telegram',
    connections?.whatsapp?.connected && 'WhatsApp',
  ].filter(Boolean);

  // Build payment methods summary
  const paymentMethods = [
    connections?.stripe?.connected && 'Stripe',
    connections?.paypal?.connected && 'PayPal',
    connections?.hotmart?.connected && 'Hotmart',
  ].filter(Boolean);

  // Main menu
  if (section === 'main') {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Ajustes</h1>
          <p className="text-gray-400">Configura tu clon y preferencias</p>
        </div>

        <div className="space-y-3">
          {/* Producto */}
          <button
            onClick={() => setSection('producto')}
            className="w-full bg-gray-900 rounded-xl p-4 hover:bg-gray-800 transition-colors text-left"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                  <Package className="text-purple-500" size={20} />
                </div>
                <div>
                  <p className="font-medium text-white">Producto</p>
                  <p className="text-sm text-gray-400">
                    {products.length > 0
                      ? `${products[0].name}${products[0].price ? ` · €${products[0].price}` : ''}`
                      : 'Sin configurar'}
                  </p>
                </div>
              </div>
              <ChevronRight className="text-gray-500" />
            </div>
          </button>

          {/* Pagos */}
          <button
            onClick={() => setSection('pagos')}
            className="w-full bg-gray-900 rounded-xl p-4 hover:bg-gray-800 transition-colors text-left"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-green-500/20 flex items-center justify-center">
                  <CreditCard className="text-green-500" size={20} />
                </div>
                <div>
                  <p className="font-medium text-white">Métodos de pago</p>
                  <p className="text-sm text-gray-400">
                    {paymentMethods.length > 0
                      ? `${paymentMethods.length} configurados`
                      : 'Sin configurar'}
                  </p>
                </div>
              </div>
              <ChevronRight className="text-gray-500" />
            </div>
          </button>

          {/* Conexiones */}
          <button
            onClick={() => setSection('conexiones')}
            className="w-full bg-gray-900 rounded-xl p-4 hover:bg-gray-800 transition-colors text-left"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-pink-500/20 flex items-center justify-center">
                  <Link2 className="text-pink-500" size={20} />
                </div>
                <div>
                  <p className="font-medium text-white">Conexiones</p>
                  <p className="text-sm text-gray-400">
                    {connectedPlatforms.length > 0
                      ? connectedPlatforms.join(' · ')
                      : 'Ninguna'}
                  </p>
                </div>
              </div>
              <ChevronRight className="text-gray-500" />
            </div>
          </button>

          {/* Calendario */}
          <button
            onClick={() => setSection('calendario')}
            className="w-full bg-gray-900 rounded-xl p-4 hover:bg-gray-800 transition-colors text-left"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                  <Calendar className="text-blue-500" size={20} />
                </div>
                <div>
                  <p className="font-medium text-white">Calendario</p>
                  <p className="text-sm text-gray-400">
                    {bookingLinks.length > 0
                      ? `${bookingLinks.length} tipos de llamada`
                      : 'Desactivado'}
                  </p>
                </div>
              </div>
              <ChevronRight className="text-gray-500" />
            </div>
          </button>

          {/* Automatizaciones */}
          <button
            onClick={() => setSection('automatizaciones')}
            className="w-full bg-gray-900 rounded-xl p-4 hover:bg-gray-800 transition-colors text-left"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-yellow-500/20 flex items-center justify-center">
                  <Zap className="text-yellow-500" size={20} />
                </div>
                <div>
                  <p className="font-medium text-white">Automatizaciones</p>
                  <p className="text-sm text-gray-400">Follow-ups y secuencias</p>
                </div>
              </div>
              <ChevronRight className="text-gray-500" />
            </div>
          </button>

          {/* Tu Clon */}
          <button
            onClick={() => setSection('clon')}
            className="w-full bg-gray-900 rounded-xl p-4 hover:bg-gray-800 transition-colors text-left"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center">
                  <Bot className="text-purple-500" size={20} />
                </div>
                <div>
                  <p className="font-medium text-white">Tu Clon</p>
                  <p className="text-sm text-gray-400">
                    Personalidad y contenido
                  </p>
                </div>
              </div>
              <ChevronRight className="text-gray-500" />
            </div>
          </button>
        </div>
      </div>
    );
  }

  // Sub-sections
  const sectionComponents: Record<Section, JSX.Element> = {
    main: <></>,
    producto: <ProductoSection onBack={() => setSection('main')} />,
    pagos: <PagosSection onBack={() => setSection('main')} />,
    conexiones: <ConexionesSection onBack={() => setSection('main')} />,
    calendario: <CalendarioSection onBack={() => setSection('main')} />,
    automatizaciones: <AutomatizacionesSection onBack={() => setSection('main')} />,
    clon: <TuClonSection onBack={() => setSection('main')} />,
  };

  return sectionComponents[section];
}
