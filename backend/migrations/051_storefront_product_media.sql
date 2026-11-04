-- Verified merchant-uploaded product images. Store thumbnails, not originals or EXIF.
-- Every public image is checked against the live, published catalog at read time.
CREATE TABLE storefront_product_media (
    tenant text NOT NULL,
    product text NOT NULL,
    image bytea NOT NULL,
    mime text NOT NULL DEFAULT 'image/jpeg' CHECK (mime='image/jpeg'),
    width integer NOT NULL CHECK (width BETWEEN 1 AND 1200),
    height integer NOT NULL CHECK (height BETWEEN 1 AND 1200),
    updated timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant,product),
    FOREIGN KEY(tenant,product) REFERENCES products(tenant,id) ON DELETE CASCADE,
    CHECK(octet_length(image) BETWEEN 100 AND 600000)
);
