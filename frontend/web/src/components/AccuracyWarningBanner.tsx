export function AccuracyWarningBanner({ message }: { message: string }) {
  return (
    <div
      className="mb-4 rounded-md border border-amber-300 bg-amber-50 px-4 py-3
      text-sm text-amber-800"
    >
      <strong>Accuracy warning:</strong> {message}
    </div>
  );
}
