import { useState, useEffect } from 'react';
import './Modal.css';

interface ModalProps {
    isOpen: boolean;
    title: string;
    onClose: () => void;
    onConfirm: (value: string) => void;
    placeholder?: string;
    confirmText?: string;
    cancelText?: string;
}

export function Modal({
    isOpen,
    title,
    onClose,
    onConfirm,
    placeholder = 'Ingrese un motivo...',
    confirmText = 'Confirmar',
    cancelText = 'Cancelar',
}: ModalProps) {
    const [value, setValue] = useState('');

    useEffect(() => {
        if (isOpen) {
            setValue('');
        }
    }, [isOpen]);

    if (!isOpen) return null;

    const handleConfirm = () => {
        onConfirm(value);
        setValue('');
    };

    const handleBackdropClick = (e: React.MouseEvent) => {
        if (e.target === e.currentTarget) {
            onClose();
        }
    };

    return (
        <div className="modal-backdrop" onClick={handleBackdropClick}>
            <div className="modal-content">
                <div className="modal-header">
                    <h3>{title}</h3>
                    <button className="modal-close" onClick={onClose}>
                        ×
                    </button>
                </div>
                <div className="modal-body">
                    <textarea
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        placeholder={placeholder}
                        rows={4}
                        autoFocus
                    />
                </div>
                <div className="modal-footer">
                    <button className="btn btn-secondary" onClick={onClose}>
                        {cancelText}
                    </button>
                    <button className="btn btn-primary" onClick={handleConfirm}>
                        {confirmText}
                    </button>
                </div>
            </div>
        </div>
    );
}
