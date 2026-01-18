// Simple error toast/banner component (no dependencies)
import { useEffect, useState } from 'react';
import './ErrorToast.css';

export interface ErrorToastProps {
    error: {
        message: string;
        type?: 'auth' | 'forbidden' | 'server' | 'network' | 'unknown';
    } | null;
    onClose: () => void;
}

export function ErrorToast({ error, onClose }: ErrorToastProps) {
    const [isVisible, setIsVisible] = useState(false);

    useEffect(() => {
        if (error) {
            setIsVisible(true);
            // Auto-hide after 5 seconds (except auth errors)
            if (error.type !== 'auth') {
                const timer = setTimeout(() => {
                    setIsVisible(false);
                    setTimeout(onClose, 300); // Wait for fade out
                }, 5000);
                return () => clearTimeout(timer);
            }
        } else {
            setIsVisible(false);
        }
    }, [error, onClose]);

    if (!error) return null;

    const getIcon = () => {
        switch (error.type) {
            case 'auth':
                return '🔒';
            case 'forbidden':
                return '🚫';
            case 'server':
                return '⚠️';
            case 'network':
                return '📡';
            default:
                return '❌';
        }
    };

    const getTypeLabel = () => {
        switch (error.type) {
            case 'auth':
                return 'Sesión expirada';
            case 'forbidden':
                return 'Sin permisos';
            case 'server':
                return 'Error del servidor';
            case 'network':
                return 'Error de conexión';
            default:
                return 'Error';
        }
    };

    return (
        <div className={`errorToast ${isVisible ? 'visible' : ''} ${error.type || ''}`}>
            <span className="errorIcon">{getIcon()}</span>
            <div className="errorContent">
                <strong>{getTypeLabel()}</strong>
                <p>{error.message}</p>
            </div>
            <button className="errorClose" onClick={() => {
                setIsVisible(false);
                setTimeout(onClose, 300);
            }}>
                ×
            </button>
        </div>
    );
}
