const PlatformLogo = ({ platform, size = 20 }: { platform: string; size?: number }) => {
  switch (platform) {
    case "instagram":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <defs>
            <linearGradient id="ig-grad" x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#FFDC80"/>
              <stop offset="25%" stopColor="#F77737"/>
              <stop offset="50%" stopColor="#E1306C"/>
              <stop offset="75%" stopColor="#C13584"/>
              <stop offset="100%" stopColor="#833AB4"/>
            </linearGradient>
          </defs>
          <rect width="24" height="24" rx="6" fill="url(#ig-grad)"/>
          <circle cx="12" cy="12" r="4" stroke="white" strokeWidth="2" fill="none"/>
          <circle cx="17.5" cy="6.5" r="1.5" fill="white"/>
        </svg>
      );
    case "telegram":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="12" fill="#0088CC"/>
          <path d="M5 12l2.5 2 2-4 7-3-1.5 9-4-2-2 3-1-4z" fill="white"/>
        </svg>
      );
    case "whatsapp":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="12" fill="#25D366"/>
          <path d="M17 14.5c-.3-.15-1.7-.85-2-1-.3-.1-.5-.15-.7.15-.2.3-.8 1-.95 1.2-.2.2-.35.2-.65.05-.3-.15-1.3-.5-2.4-1.5-.9-.8-1.5-1.8-1.7-2.1-.15-.3 0-.45.15-.6.1-.1.3-.3.4-.45.15-.15.2-.25.3-.45.1-.2 0-.35-.05-.5-.05-.15-.7-1.7-.95-2.3-.25-.6-.5-.5-.7-.5h-.6c-.2 0-.5.05-.75.35-.25.3-1 1-1 2.4s1 2.8 1.15 3c.15.2 2 3 4.8 4.2.7.3 1.2.5 1.65.6.7.2 1.3.15 1.8.1.55-.1 1.7-.7 1.95-1.4.25-.7.25-1.25.15-1.4-.05-.1-.25-.2-.55-.35z" fill="white"/>
        </svg>
      );
    case "stripe":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#635BFF"/>
          <path d="M11 8c-1.5 0-2.5.5-2.5 1.5 0 2 4 1.5 4 3 0 .7-.7 1.5-2.5 1.5-1.5 0-2.5-.5-3-1v2c.5.5 1.5 1 3 1 2 0 3.5-1 3.5-2.5 0-2.5-4-2-4-3.5 0-.5.5-1 1.5-1 1 0 2 .3 2.5.7V8.5c-.5-.3-1.5-.5-2.5-.5z" fill="white"/>
        </svg>
      );
    case "paypal":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#003087"/>
          <path d="M9 6h4c2 0 3 1 3 2.5S15 11 13 11h-2l-.5 3H8l1-8zm2 3h1.5c.5 0 1-.3 1-.8 0-.4-.3-.7-.8-.7H11l-.2 1.5h.2z" fill="white"/>
          <path d="M7 9h4c2 0 3 1 3 2.5S13 14 11 14H9l-.5 3H6l1-8z" fill="#009CDE"/>
        </svg>
      );
    case "google":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#fff"/>
          <path d="M12 4L4 8v8l8 4 8-4V8l-8-4z" fill="#00897B"/>
          <path d="M12 4l8 4v8" fill="#00AC47"/>
          <path d="M12 4L4 8v8" fill="#4285F4"/>
          <path d="M12 20l8-4" fill="#FFBA00"/>
          <path d="M12 20L4 16" fill="#EA4335"/>
          <circle cx="12" cy="12" r="3" fill="white"/>
        </svg>
      );
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#6366F1"/>
          <circle cx="12" cy="12" r="4" stroke="white" strokeWidth="2"/>
        </svg>
      );
  }
};

export default PlatformLogo;
