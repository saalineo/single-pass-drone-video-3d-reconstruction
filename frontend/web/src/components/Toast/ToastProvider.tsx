import { Toaster } from 'react-hot-toast';

export function ToastProvider() {
  return <Toaster position="bottom-right" toastOptions={{ duration: 5000 }} />;
}
