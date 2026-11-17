import Icon from "./Icon.jsx";

export default function PaginationControls({ page, totalPages, onPrev, onNext }) {
  if (totalPages <= 1) return null;

  return (
    <div className="pagination">
      <button className="ghost" type="button" onClick={onPrev} disabled={page <= 1}>
        <Icon name="chevronLeft" size={16} /> Previous
      </button>
      <span className="pagination-label">
        Page <strong>{page}</strong> of {totalPages}
      </span>
      <button className="ghost" type="button" onClick={onNext} disabled={page >= totalPages}>
        Next <Icon name="chevronRight" size={16} />
      </button>
    </div>
  );
}
