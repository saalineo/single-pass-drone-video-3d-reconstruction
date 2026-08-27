export interface LayerVisibility {
  aoi: boolean;
  trajectory: boolean;
  coverage: boolean;
}

const LABEL: Record<keyof LayerVisibility, string> = {
  aoi: 'AOI',
  trajectory: 'Trajectory',
  coverage: 'Coverage',
};

export function LayerToggle({
  visibility,
  onChange,
  disabled,
}: {
  visibility: LayerVisibility;
  onChange: (next: LayerVisibility) => void;
  disabled?: Partial<Record<keyof LayerVisibility, boolean>>;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-white/90 px-3 py-2 text-xs shadow">
      {(Object.keys(LABEL) as (keyof LayerVisibility)[]).map((key) => (
        <label key={key} className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={visibility[key]}
            disabled={disabled?.[key]}
            onChange={(e) => onChange({ ...visibility, [key]: e.target.checked })}
          />
          {LABEL[key]}
        </label>
      ))}
    </div>
  );
}
