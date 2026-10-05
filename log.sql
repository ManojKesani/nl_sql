-- SELECT b.id, b.title
--         FROM books b
--         JOIN publishers p ON b.publisher_id = p.id
--         WHERE p.publisher = 'Yale University Press';

--  SELECT "title" FROM "books" WHERE "publisher_id" IN (
--  SELECT "id" FROM "publishers" WHERE "publisher" = 'Yale University Press'
--  );

-- SELECT b.id, b.title 
-- FROM books b 
-- JOIN publishers p 
-- ON b.publisher_id = p.id 
-- WHERE p.publisher = 'Yale University Press';

-- SELECT title,  author, isbn FROM books WHERE publisher = 'Yale University Press';
-- SELECT DISTINCT format FROM books;
-- SELECT published FROM books LIMIT 5;
-- SELECT MIN(year), MAX(year) FROM books;
-- SELECT COUNT(*) FROM books WHERE published IS NULL OR published = '';
-- SELECT b.* FROM books b JOIN publishers p ON p.id = b.publisher_id WHERE p.publisher = 'Yale University Press';
-- SELECT AVG(r.rating) AS average_rating FROM books b JOIN ratings r ON 
--         r.book_id = b.id WHERE LOWER(b.title) = 'the years';
-- SELECT AVG(ratings.rating) AS average_rating
-- FROM books
-- JOIN ratings ON ratings.book_id = books.id
-- WHERE books.title = 'The Years';

-- SELECT AVG(r.rating) AS avg_rating FROM books b JOIN ratings r ON r.book_id = b.id WHERE b.title = 'The Years';
SELECT b.id, b.title, b.isbn, b.published FROM books b JOIN publishers p ON p.id = b.publisher_id WHERE p.publisher = 'Yale University Press' ORDER BY b.title;
SELECT COUNT(*) AS hardcover_count FROM books WHERE format = 'hardcover';