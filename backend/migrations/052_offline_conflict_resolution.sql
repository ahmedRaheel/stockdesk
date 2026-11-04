-- Preserve rejected replay evidence; corrections are separate audited decisions.
CREATE TABLE offline_operation_resolutions (
    tenant text NOT NULL,
    device text NOT NULL,
    operation_id text NOT NULL,
    resolution text NOT NULL CHECK(resolution IN ('replaced','dismissed')),
    replacement_sale text,
    notes text NOT NULL CHECK(length(notes) BETWEEN 5 AND 500),
    actor text NOT NULL REFERENCES users(id),
    resolved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant,device,operation_id),
    FOREIGN KEY(tenant,device,operation_id) REFERENCES offline_operations(tenant,device,operation_id),
    FOREIGN KEY(tenant,replacement_sale) REFERENCES sales(tenant,id),
    CHECK((resolution='replaced' AND replacement_sale IS NOT NULL)
       OR (resolution='dismissed' AND replacement_sale IS NULL))
);
CREATE UNIQUE INDEX offline_resolution_unique_replacement
 ON offline_operation_resolutions(tenant,replacement_sale)
 WHERE replacement_sale IS NOT NULL;
