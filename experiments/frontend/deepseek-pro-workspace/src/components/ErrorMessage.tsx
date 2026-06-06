'use client';

interface ErrorMessageProps {
  message: string;
  onRetry?: () => void;
}

export default function ErrorMessage({ message, onRetry }: ErrorMessageProps) {
  return (
    <div className="error-message" role="alert">
      <p className="error-icon">⚠</p>
      <div className="error-body">
        <p className="error-text">{message}</p>
        {onRetry && (
          <button type="button" className="error-retry" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
